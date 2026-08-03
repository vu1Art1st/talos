"""漏洞知识库：按漏洞名称维护标准描述 / 危害说明 / 修复建议模板。

每个漏洞名称至多一条，同一漏洞类型可含多条；支持批量导入（按名称 upsert）与批量删除。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.query import get_or_404
from app.constants import VUL_LEVEL, VUL_TYPE
from app.core.deps import get_current_user, require_perm
from app.db import get_session
from app.models import KnowledgeEntry, Vul
from app.models.user import User
from app.schemas import KnowledgeBatchDeleteIn, KnowledgeBatchIn, KnowledgeIn, KnowledgeOut

router = APIRouter(prefix="/knowledge", tags=["漏洞知识库"])


def _validate_dict_codes(body: KnowledgeIn) -> None:
    """校验字典码合法性（Pydantic 负责格式，这里负责业务字典成员）。"""
    if body.vul_type not in VUL_TYPE:
        raise HTTPException(400, f"未知的漏洞类型：{body.vul_type}")
    if body.severity_level not in VUL_LEVEL:
        raise HTTPException(400, f"未知的危害等级：{body.severity_level}")


def _apply_body(entry: KnowledgeEntry, body: KnowledgeIn, user: User) -> None:
    for k, v in body.model_dump().items():
        setattr(entry, k, v)
    entry.creator_id = user.id
    entry.username = user.realname or user.username


@router.get("", response_model=list[KnowledgeOut])
async def list_entries(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return (
        await session.execute(
            select(KnowledgeEntry).order_by(
                KnowledgeEntry.severity_level, KnowledgeEntry.vul_type, KnowledgeEntry.id
            )
        )
    ).scalars().all()


@router.get("/by-type/{vul_type}", response_model=KnowledgeOut)
async def get_by_type(
    vul_type: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """按漏洞类型取模板（提交/编辑页「一键套用模板」入口）。

    同类型存在多条时返回危害等级最高（数值最小）、最早创建的一条。
    """
    entry = (
        await session.execute(
            select(KnowledgeEntry)
            .where(KnowledgeEntry.vul_type == vul_type)
            .order_by(KnowledgeEntry.severity_level, KnowledgeEntry.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "该漏洞类型暂无知识库模板")
    return entry


@router.post("", response_model=KnowledgeOut)
async def upsert_entry(
    body: KnowledgeIn,
    user: User = Depends(require_perm("vuln:manage")),
    session: AsyncSession = Depends(get_session),
):
    """新建或更新条目：每个漏洞名称至多一条，存在则覆盖。"""
    _validate_dict_codes(body)
    entry = (
        await session.execute(
            select(KnowledgeEntry).where(KnowledgeEntry.vulnerability_name == body.vulnerability_name)
        )
    ).scalar_one_or_none()
    if entry is None:
        entry = KnowledgeEntry(vulnerability_name=body.vulnerability_name)
        session.add(entry)
    _apply_body(entry, body, user)
    await session.commit()
    await session.refresh(entry)
    return entry


@router.put("/{entry_id}", response_model=KnowledgeOut)
async def update_entry(
    entry_id: int,
    body: KnowledgeIn,
    user: User = Depends(require_perm("vuln:manage")),
    session: AsyncSession = Depends(get_session),
):
    """按 ID 编辑条目；改名时校验与其他条目不冲突。"""
    _validate_dict_codes(body)
    entry = await get_or_404(session, KnowledgeEntry, entry_id, "知识库条目不存在")
    dup = (
        await session.execute(
            select(KnowledgeEntry.id).where(
                KnowledgeEntry.vulnerability_name == body.vulnerability_name,
                KnowledgeEntry.id != entry_id,
            )
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(400, f"漏洞名称已存在：{body.vulnerability_name}")
    _apply_body(entry, body, user)
    await session.commit()
    await session.refresh(entry)
    return entry


@router.post("/batch-import")
async def batch_import(
    body: KnowledgeBatchIn,
    user: User = Depends(require_perm("vuln:manage")),
    session: AsyncSession = Depends(get_session),
):
    """批量导入：按漏洞名称 upsert。任一条目字典码非法则整批拒绝（事务性）。"""
    # 批内名称查重：同名条目重复出现视为数据错误
    names = [item.vulnerability_name for item in body.items]
    dup_names = {n for n in names if names.count(n) > 1}
    if dup_names:
        raise HTTPException(400, f"导入数据内漏洞名称重复：{'、'.join(sorted(dup_names))}")
    for i, item in enumerate(body.items, start=1):
        if item.vul_type not in VUL_TYPE:
            raise HTTPException(400, f"第 {i} 条（{item.vulnerability_name}）漏洞类型非法：{item.vul_type}")
        if item.severity_level not in VUL_LEVEL:
            raise HTTPException(400, f"第 {i} 条（{item.vulnerability_name}）危害等级非法：{item.severity_level}")

    existing = {
        e.vulnerability_name: e
        for e in (
            await session.execute(
                select(KnowledgeEntry).where(KnowledgeEntry.vulnerability_name.in_(names))
            )
        ).scalars().all()
    }
    created = updated = 0
    for item in body.items:
        entry = existing.get(item.vulnerability_name)
        if entry is None:
            entry = KnowledgeEntry(vulnerability_name=item.vulnerability_name)
            session.add(entry)
            created += 1
        else:
            updated += 1
        _apply_body(entry, item, user)
    await session.commit()
    return {"created": created, "updated": updated, "total": created + updated}


@router.post("/batch-delete")
async def batch_delete(
    body: KnowledgeBatchDeleteIn,
    _: User = Depends(require_perm("vuln:manage")),
    session: AsyncSession = Depends(get_session),
):
    """批量删除：按 ID 列表删除，忽略不存在的 ID。"""
    result = await session.execute(
        sa_delete(KnowledgeEntry).where(KnowledgeEntry.id.in_(body.ids))
    )
    await session.commit()
    return {"deleted": result.rowcount, "msg": "删除成功"}


@router.post("/from-vul/{vul_id}", response_model=KnowledgeOut)
async def save_from_vul(
    vul_id: int,
    user: User = Depends(require_perm("vuln:manage")),
    session: AsyncSession = Depends(get_session),
):
    """从已有高质量漏洞记录「存为模板」：按漏洞标题作为名称 upsert 描述与修复建议。"""
    vul = await get_or_404(session, Vul, vul_id, "漏洞不存在")
    name = (vul.title or "").strip()
    if not name:
        raise HTTPException(400, "漏洞标题为空，无法存为模板")
    entry = (
        await session.execute(
            select(KnowledgeEntry).where(KnowledgeEntry.vulnerability_name == name)
        )
    ).scalar_one_or_none()
    if entry is None:
        entry = KnowledgeEntry(vulnerability_name=name, vul_type=vul.vul_type)
        session.add(entry)
    entry.vul_type = vul.vul_type
    entry.severity_level = vul.level
    entry.description_html = vul.description_html
    entry.description_json = vul.description_json
    entry.solution_html = vul.solution_html
    entry.solution_json = vul.solution_json
    entry.creator_id = user.id
    entry.username = user.realname or user.username
    await session.commit()
    await session.refresh(entry)
    return entry


@router.delete("/{entry_id}")
async def delete_entry(
    entry_id: int,
    _: User = Depends(require_perm("vuln:manage")),
    session: AsyncSession = Depends(get_session),
):
    entry = await session.get(KnowledgeEntry, entry_id)
    if entry:
        await session.delete(entry)
        await session.commit()
    return {"msg": "删除成功"}
