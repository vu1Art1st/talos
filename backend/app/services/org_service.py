"""组织（部门）解析与资产负责人同步的唯一入口。

资产通过 `group_id` 关联组织，`department` 仅作为展示名并由组织名规范化；
成员去重口径固定为「同组织同名」，跨组织允许同名人员存在。
"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Group, GroupMember


async def find_group_by_name(session: AsyncSession, name: str) -> Group | None:
    """按组织名精确查询（忽略首尾空白）。"""
    key = (name or "").strip()
    if not key:
        return None
    return (
        await session.execute(select(Group).where(Group.name == key))
    ).scalar_one_or_none()


async def ensure_group(session: AsyncSession, name: str) -> tuple[Group, bool]:
    """取组织，不存在则创建；返回 (组织, 是否新建)。

    并发同名由唯一约束 + savepoint 兜底：冲突时回查已存在行，保证幂等。
    """
    key = (name or "").strip()
    if not key:
        raise ValueError("组织名称不能为空")
    existing = await find_group_by_name(session, key)
    if existing is not None:
        return existing, False
    try:
        async with session.begin_nested():
            group = Group(name=key)
            session.add(group)
    except IntegrityError:
        existing = await find_group_by_name(session, key)
        if existing is None:
            raise
        return existing, False
    return group, True


async def resolve_asset_group(
    session: AsyncSession,
    *,
    group_id: int | None,
    department: str,
    create_group: bool,
) -> Group | None:
    """把资产的 `group_id` / `department` 解析成一个组织。

    - 显式 group_id 优先；
    - 其次按部门名精确匹配；
    - 均未命中且 create_group 为真时自动创建；
    - 其余返回 None（由路由决定是否报错）。
    """
    if group_id is not None:
        return await session.get(Group, group_id)
    group = await find_group_by_name(session, department)
    if group is not None:
        return group
    if create_group and (department or "").strip():
        group, _ = await ensure_group(session, department)
        return group
    return None


async def sync_owners_to_group_members(
    session: AsyncSession, group_id: int, owners: list[dict],
) -> int:
    """把资产负责人同步到指定组织，返回新增成员数。

    - 只在该组织范围内按姓名去重，跨组织同名不跳过；
    - 同名已存在时仅补全空白的电话/邮箱，不覆盖已有值。
    """
    if not owners:
        return 0
    rows = (
        await session.execute(select(GroupMember).where(GroupMember.group_id == group_id))
    ).scalars().all()
    existing = {m.name: m for m in rows}
    seen = set(existing)
    added = 0
    for o in owners:
        name = (o.get("name") or "").strip()
        if not name:
            continue
        phone = (o.get("phone") or "").strip()
        email = (o.get("email") or "").strip()
        member = existing.get(name)
        if member is not None:
            if not member.phone and phone:
                member.phone = phone
            if not member.email and email:
                member.email = email
        elif name not in seen:
            session.add(GroupMember(group_id=group_id, name=name, phone=phone, email=email))
            seen.add(name)
            added += 1
    return added
