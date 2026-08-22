from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.auth import build_user_out
from app.constants import PERMISSIONS
from app.core.deps import get_current_user, require_any_perm, require_perm
from app.core.query import get_or_404, paginate, apply_sort
from app.core.security import hash_password
from app.db import get_session
from app.models import Group, GroupMember, Role, User
from app.schemas import GroupIn, GroupOut, GroupMemberIn, GroupMemberOut, Page, RoleIn, RoleOut, UserIn, UserOption, UserOut
from app.services.audit_service import audit

router = APIRouter(tags=["用户与权限"])


# ---------- 用户 ----------
@router.get("/users", response_model=Page[UserOut])
async def list_users(
    search: str = "",
    sort: str = "",
    order: str = "desc",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_perm("user:manage")),
    session: AsyncSession = Depends(get_session),
):
    cond = []
    if search:
        cond.append(User.username.ilike(f"%{search}%") | User.realname.ilike(f"%{search}%"))
    stmt = select(User).options(selectinload(User.role)).where(*cond)
    stmt = apply_sort(
        stmt, User, sort, order,
        {"id", "username", "realname", "email", "is_active", "create_time", "last_login"},
        User.id.desc(),
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
    request: Request,
    operator: User = Depends(require_perm("user:manage")),
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
    await audit(session, request, "user_create", operator, {"target": f"users/{user.id}", "username": user.username})
    return build_user_out(user)


@router.put("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserIn,
    request: Request,
    operator: User = Depends(require_perm("user:manage")),
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
    await audit(session, request, "user_update", operator, {"target": f"users/{user.id}", "username": user.username})
    return build_user_out(user)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    request: Request,
    current: User = Depends(require_perm("user:manage")),
    session: AsyncSession = Depends(get_session),
):
    if user_id == current.id:
        raise HTTPException(400, "不能删除当前登录账号")
    user = await session.get(User, user_id)
    if user:
        await session.delete(user)
        await session.commit()
        await audit(session, request, "user_delete", current, {"target": f"users/{user_id}", "username": user.username})
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
    request: Request,
    operator: User = Depends(require_perm("user:manage")),
    session: AsyncSession = Depends(get_session),
):
    role = Role(name=body.name, permissions=body.permissions, remark=body.remark)
    session.add(role)
    await session.commit()
    await session.refresh(role)
    await audit(session, request, "role_update", operator, {"op": "create", "role": role.name})
    return role


@router.put("/roles/{role_id}", response_model=RoleOut)
async def update_role(
    role_id: int,
    body: RoleIn,
    request: Request,
    operator: User = Depends(require_perm("user:manage")),
    session: AsyncSession = Depends(get_session),
):
    role = await get_or_404(session, Role, role_id, "角色不存在")
    role.name = body.name
    role.permissions = body.permissions
    role.remark = body.remark
    await session.commit()
    await audit(session, request, "role_update", operator, {"op": "update", "role": role.name})
    return role


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: int,
    request: Request,
    operator: User = Depends(require_perm("user:manage")),
    session: AsyncSession = Depends(get_session),
):
    used = (await session.execute(select(func.count(User.id)).where(User.role_id == role_id))).scalar_one()
    if used:
        raise HTTPException(400, "角色下仍有用户，无法删除")
    role = await session.get(Role, role_id)
    if role:
        name = role.name
        await session.delete(role)
        await session.commit()
        await audit(session, request, "role_update", operator, {"op": "delete", "role": name})
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
    group = Group(name=name, remark=body.remark)
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


# ---------- 组织成员 ----------
@router.get("/groups/{group_id}/members", response_model=list[GroupMemberOut])
async def list_group_members(
    group_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """组织成员列表（登录用户可读）。"""
    await get_or_404(session, Group, group_id, "组织不存在")
    return (
        await session.execute(
            select(GroupMember).where(GroupMember.group_id == group_id).order_by(GroupMember.id)
        )
    ).scalars().all()


@router.post("/groups/{group_id}/members", response_model=GroupMemberOut)
async def create_group_member(
    group_id: int,
    body: GroupMemberIn,
    _: User = Depends(require_perm("user:manage")),
    session: AsyncSession = Depends(get_session),
):
    """组织录入人员：姓名/电话/邮箱。"""
    await get_or_404(session, Group, group_id, "组织不存在")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "姓名不能为空")
    member = GroupMember(
        group_id=group_id, name=name,
        phone=body.phone.strip(), email=body.email.strip(),
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


@router.put("/groups/{group_id}/members/{member_id}", response_model=GroupMemberOut)
async def update_group_member(
    group_id: int,
    member_id: int,
    body: GroupMemberIn,
    _: User = Depends(require_perm("user:manage")),
    session: AsyncSession = Depends(get_session),
):
    """编辑组织成员。"""
    member = await get_or_404(session, GroupMember, member_id, "成员不存在")
    if member.group_id != group_id:
        raise HTTPException(400, "成员不属于该组织")
    member.name = body.name.strip()
    member.phone = body.phone.strip()
    member.email = body.email.strip()
    await session.commit()
    await session.refresh(member)
    return member


@router.delete("/groups/{group_id}/members/{member_id}")
async def delete_group_member(
    group_id: int,
    member_id: int,
    _: User = Depends(require_perm("user:manage")),
    session: AsyncSession = Depends(get_session),
):
    """删除组织成员。"""
    member = await get_or_404(session, GroupMember, member_id, "成员不存在")
    if member.group_id != group_id:
        raise HTTPException(400, "成员不属于该组织")
    await session.delete(member)
    await session.commit()
    return {"msg": "删除成功"}


@router.get("/group-members/all", response_model=list[GroupMemberOut])
async def list_all_group_members(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """全部组织成员聚合列表，供资产「系统负责人」下拉选择。"""
    return (
        await session.execute(select(GroupMember).order_by(GroupMember.group_id, GroupMember.id))
    ).scalars().all()
