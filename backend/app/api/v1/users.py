from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.auth import build_user_out
from app.constants import PERMISSIONS
from app.core.deps import get_current_user, require_any_perm, require_perm
from app.core.query import get_or_404, paginate
from app.core.security import hash_password
from app.db import get_session
from app.models import Group, Role, User
from app.schemas import GroupIn, GroupOut, Page, RoleIn, RoleOut, UserIn, UserOption, UserOut

router = APIRouter(tags=["用户与权限"])


# ---------- 用户 ----------
@router.get("/users", response_model=Page[UserOut])
async def list_users(
    search: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_perm("user:manage")),
    session: AsyncSession = Depends(get_session),
):
    cond = []
    if search:
        cond.append(User.username.ilike(f"%{search}%") | User.realname.ilike(f"%{search}%"))
    stmt = (
        select(User).options(selectinload(User.role)).where(*cond).order_by(User.id.desc())
    )
    total, users = await paginate(session, stmt, page, size)
    return Page(total=total, items=[build_user_out(u) for u in users])


@router.get("/users/options", response_model=list[UserOption])
async def list_user_options(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """启用用户的姓名列表，供报告作者等下拉选择，无需 user:manage 权限。"""
    users = (
        await session.execute(select(User).where(User.is_active.is_(True)).order_by(User.id))
    ).scalars().all()
    return [UserOption(id=u.id, name=u.realname or u.username) for u in users]


@router.post("/users", response_model=UserOut)
async def create_user(
    body: UserIn,
    _: User = Depends(require_perm("user:manage")),
    session: AsyncSession = Depends(get_session),
):
    exists = (await session.execute(select(User).where(User.username == body.username))).scalar_one_or_none()
    if exists:
        raise HTTPException(400, "用户名已存在")
    if not body.password:
        raise HTTPException(400, "初始密码不能为空")
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        realname=body.realname,
        email=body.email,
        phone=body.phone,
        is_active=body.is_active,
        role_id=body.role_id,
        must_change_password=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return build_user_out(user)


@router.put("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserIn,
    _: User = Depends(require_perm("user:manage")),
    session: AsyncSession = Depends(get_session),
):
    user = await get_or_404(session, User, user_id, "用户不存在")
    user.realname = body.realname
    user.email = body.email
    user.phone = body.phone
    # 由启用转为禁用：递增令牌版本，强制已登录会话失效
    if user.is_active and not body.is_active:
        user.token_version += 1
    user.is_active = body.is_active
    user.role_id = body.role_id
    if body.password:
        user.password_hash = hash_password(body.password)
        user.must_change_password = True
        # 重置密码同样失效存量令牌
        user.token_version += 1
    await session.commit()
    await session.refresh(user)
    return build_user_out(user)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current: User = Depends(require_perm("user:manage")),
    session: AsyncSession = Depends(get_session),
):
    if user_id == current.id:
        raise HTTPException(400, "不能删除当前登录账号")
    user = await session.get(User, user_id)
    if user:
        await session.delete(user)
        await session.commit()
    return {"msg": "删除成功"}


# ---------- 角色 ----------
@router.get("/roles", response_model=list[RoleOut])
async def list_roles(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    roles = (await session.execute(select(Role).order_by(Role.id))).scalars().all()
    return roles


@router.get("/roles/permissions", response_model=list[str])
async def list_permissions(_: User = Depends(get_current_user)):
    return PERMISSIONS


@router.post("/roles", response_model=RoleOut)
async def create_role(
    body: RoleIn,
    _: User = Depends(require_perm("user:manage")),
    session: AsyncSession = Depends(get_session),
):
    role = Role(name=body.name, permissions=body.permissions, remark=body.remark)
    session.add(role)
    await session.commit()
    await session.refresh(role)
    return role


@router.put("/roles/{role_id}", response_model=RoleOut)
async def update_role(
    role_id: int,
    body: RoleIn,
    _: User = Depends(require_perm("user:manage")),
    session: AsyncSession = Depends(get_session),
):
    role = await get_or_404(session, Role, role_id, "角色不存在")
    role.name = body.name
    role.permissions = body.permissions
    role.remark = body.remark
    await session.commit()
    return role


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: int,
    _: User = Depends(require_perm("user:manage")),
    session: AsyncSession = Depends(get_session),
):
    used = (await session.execute(select(func.count(User.id)).where(User.role_id == role_id))).scalar_one()
    if used:
        raise HTTPException(400, "角色下仍有用户，无法删除")
    role = await session.get(Role, role_id)
    if role:
        await session.delete(role)
        await session.commit()
    return {"msg": "删除成功"}


# ---------- 组 ----------
@router.get("/groups", response_model=list[GroupOut])
async def list_groups(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return (await session.execute(select(Group).order_by(Group.id))).scalars().all()


@router.post("/groups", response_model=GroupOut)
async def create_group(
    body: GroupIn,
    # 测试计划「所属部门」下拉支持就地新增组织，故 special:manage 亦可创建
    _: User = Depends(require_any_perm("user:manage", "special:manage")),
    session: AsyncSession = Depends(get_session),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "组织名称不能为空")
    exists = (await session.execute(select(Group).where(Group.name == name))).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(400, "同名组织已存在")
    group = Group(
        name=name, remark=body.remark,
        owner_name=body.owner_name.strip(), owner_phone=body.owner_phone.strip(),
        owner_email=body.owner_email.strip(),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


@router.put("/groups/{group_id}", response_model=GroupOut)
async def update_group(
    group_id: int,
    body: GroupIn,
    _: User = Depends(require_perm("user:manage")),
    session: AsyncSession = Depends(get_session),
):
    group = await get_or_404(session, Group, group_id, "组不存在")
    group.name = body.name
    group.remark = body.remark
    group.owner_name = body.owner_name.strip()
    group.owner_phone = body.owner_phone.strip()
    group.owner_email = body.owner_email.strip()
    await session.commit()
    await session.refresh(group)
    return group


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: int,
    _: User = Depends(require_perm("user:manage")),
    session: AsyncSession = Depends(get_session),
):
    group = await session.get(Group, group_id)
    if group:
        await session.delete(group)
        await session.commit()
    return {"msg": "删除成功"}
