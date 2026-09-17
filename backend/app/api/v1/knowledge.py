"""漏洞模板库：按漏洞名称维护标准描述 / 危害说明 / 修复建议模板。

每个漏洞名称至多一条，同一漏洞类型可含多条；支持批量导入（按名称 upsert）与批量删除。
漏洞录入「套用模板」支持跨模板全局搜索（GET /knowledge/search），不预选漏洞类型即可
按漏洞名称 / 编号（CVE 等）/ 关键字检索，选中后按 ID 取完整条目套用。
"""
import re
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import Text, case, cast, delete as sa_delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.query import apply_sort, get_or_404, paginate, parse_int_list
from app.constants import VUL_LEVEL
from app.core.deps import get_current_user, require_perm
from app.db import get_session
from app.models import KnowledgeEntry, Vul, VulnType
from app.models.user import User
from app.schemas import (
    KnowledgeBatchDeleteIn,
    KnowledgeBatchIn,
    KnowledgeIn,
    KnowledgeOut,
    KnowledgeSearchItem,
    KnowledgeSearchOut,
)
from app.services.audit_service import audit

router = APIRouter(prefix="/knowledge", tags=["漏洞模板库"])

# ---------- 跨模板搜索：排序白名单与摘要口径 ----------
# 键为对外排序参数值，值为模型列名（apply_sort 按属性名取列）
_SEARCH_SORT_FIELDS = {
    "update_time": "update_time",
    "severity_level": "severity_level",
    "name": "vulnerability_name",
}
_SEARCH_SUMMARY_LIMIT = 80


def _esc(kw: str) -> str:
    """转义 LIKE 通配符：用户输入 % _ \\ 时按字面匹配，避免退化成全表命中。"""
    return kw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _like(kw: str) -> str:
    return f"%{_esc(kw)}%"


def _ilike(col, kw: str):
    """大小写不敏感模糊匹配（两侧通配），统一带 ESCAPE。"""
    return col.ilike(_like(kw), escape="\\")


def _plain(html: str | None, limit: int = _SEARCH_SUMMARY_LIMIT) -> str:
    """剥离 HTML 标签取纯文本摘要：列表只返回摘要，正文由详情接口按需获取。"""
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()[:limit]


async def _type_names(session: AsyncSession, codes: set[int]) -> dict[int, str]:
    """按需解析漏洞类型名称（vuln_types 是动态字典，自定义类型 code≥1000）。"""
    if not codes:
        return {}
    rows = (
        await session.execute(
            select(VulnType.code, VulnType.name).where(VulnType.code.in_(codes))
        )
    ).all()
    return {code: name for code, name in rows}


def _matched_field(entry: KnowledgeEntry, kw: str) -> str:
    """命中位置（name / references / content），供前端结果说明与高亮定位。"""
    low = kw.lower()
    if low in (entry.vulnerability_name or "").lower():
        return "name"
    if any(low in (u or "").lower() for u in (entry.references or [])):
        return "references"
    return "content"


def _to_search_item(
    entry: KnowledgeEntry, type_names: dict[int, str], kw: str
) -> KnowledgeSearchItem:
    return KnowledgeSearchItem(
        id=entry.id,
        vulnerability_name=entry.vulnerability_name,
        vul_type=entry.vul_type,
        vul_type_name=type_names.get(entry.vul_type, str(entry.vul_type)),
        severity_level=entry.severity_level,
        summary=_plain(entry.description_html or entry.harm_html or entry.solution_html),
        username=entry.username,
        update_time=entry.update_time,
        matched_field=_matched_field(entry, kw) if kw else "",
    )


async def _validate_dict_codes(session: AsyncSession, body: KnowledgeIn) -> None:
    """校验字典码合法性：漏洞类型查 vuln_types 表，危害等级沿用常量。"""
    vt = (
        await session.execute(select(VulnType).where(VulnType.code == body.vul_type))
    ).scalar_one_or_none()
    if vt is None:
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


@router.get("/search", response_model=KnowledgeSearchOut)
async def search_entries(
    q: str = Query("", max_length=64),
    vul_type: str = Query("", max_length=512),
    severity_level: str = Query("", max_length=128),
    creator: str = Query("", max_length=64),
    updated_from: date | None = None,
    updated_to: date | None = None,
    deep: bool = False,
    sort: str = Query("relevance", max_length=32),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """跨模板全局搜索漏洞模板（漏洞录入「套用模板」入口）。

    - 匹配范围：漏洞名称（含 CVE 等编号后缀）+ 参考链接；`deep=True` 追加描述 / 危害 / 修复建议正文。
    - `vul_type` 逗号分隔多选；**传空即全局搜索**，传当前漏洞类型即等价于原有「模板内搜索」。
    - 排序：`relevance`（名称全等 > 前缀 > 包含 > 参考链接 > 正文）为默认，另支持
      `update_time` / `severity_level` / `name`，非法值回退默认排序不报错。
    - 返回轻量条目（含所属漏洞类型名与摘要），完整正文由 `GET /knowledge/{id}` 按需获取。
    """
    kw = q.strip()
    stmt = select(KnowledgeEntry)
    if types := parse_int_list(vul_type):
        stmt = stmt.where(KnowledgeEntry.vul_type.in_(types))
    if levels := parse_int_list(severity_level):
        stmt = stmt.where(KnowledgeEntry.severity_level.in_(levels))
    if creator.strip():
        stmt = stmt.where(_ilike(KnowledgeEntry.username, creator.strip()))
    if updated_from:
        stmt = stmt.where(
            KnowledgeEntry.update_time >= datetime.combine(updated_from, time.min)
        )
    if updated_to:
        # 区间含当日：用「次日零点」开区间，避免当天 00:00 之后的数据被漏掉
        stmt = stmt.where(
            KnowledgeEntry.update_time
            < datetime.combine(updated_to + timedelta(days=1), time.min)
        )

    # 参考链接为 JSON 列，统一 CAST 成文本参与匹配（SQLite 存 TEXT、PG 为 json 均可转）
    refs = cast(KnowledgeEntry.references, Text)
    score = None
    if kw:
        conds = [_ilike(KnowledgeEntry.vulnerability_name, kw), _ilike(refs, kw)]
        if deep:
            conds += [
                _ilike(KnowledgeEntry.description_html, kw),
                _ilike(KnowledgeEntry.harm_html, kw),
                _ilike(KnowledgeEntry.solution_html, kw),
            ]
        stmt = stmt.where(or_(*conds))
        name = KnowledgeEntry.vulnerability_name
        score = case(
            (func.lower(name) == kw.lower(), 100),
            (name.ilike(f"{_esc(kw)}%", escape="\\"), 80),
            (name.ilike(_like(kw), escape="\\"), 60),
            (refs.ilike(_like(kw), escape="\\"), 40),
            else_=20,
        )

    if sort == "relevance" and score is not None:
        stmt = stmt.order_by(
            score.desc(), KnowledgeEntry.update_time.desc(), KnowledgeEntry.id.desc()
        )
    else:
        default_order = (
            (score.desc(), KnowledgeEntry.update_time.desc(), KnowledgeEntry.id.desc())
            if score is not None
            else (KnowledgeEntry.update_time.desc(), KnowledgeEntry.id.desc())
        )
        stmt = apply_sort(
            stmt,
            KnowledgeEntry,
            _SEARCH_SORT_FIELDS.get(sort, ""),
            order,
            set(_SEARCH_SORT_FIELDS.values()),
            default_order,
        )

    total, rows = await paginate(session, stmt, page, size)
    type_names = await _type_names(session, {r.vul_type for r in rows})
    return KnowledgeSearchOut(
        total=total, items=[_to_search_item(r, type_names, kw) for r in rows]
    )


@router.get("/{entry_id}", response_model=KnowledgeOut)
async def get_entry(
    entry_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """按 ID 取完整模板条目（含描述 / 危害 / 修复建议 / 引用 / CVSS 向量），供套用模板回填。"""
    return await get_or_404(session, KnowledgeEntry, entry_id, "知识库条目不存在")


@router.get("/by-type/{vul_type}", response_model=list[KnowledgeOut])
async def get_by_type(
    vul_type: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """按漏洞类型取模板列表（提交/编辑页「套用模板」入口）。

    返回该类型下全部模板，危害等级高（数值小）者在前；由前端弹窗选择具体条目。
    """
    return (
        await session.execute(
            select(KnowledgeEntry)
            .where(KnowledgeEntry.vul_type == vul_type)
            .order_by(KnowledgeEntry.severity_level, KnowledgeEntry.id)
        )
    ).scalars().all()


@router.post("", response_model=KnowledgeOut)
async def upsert_entry(
    body: KnowledgeIn,
    user: User = Depends(require_perm("vuln:manage")),
    session: AsyncSession = Depends(get_session),
):
    """新建或更新条目：每个漏洞名称至多一条，存在则覆盖。"""
    await _validate_dict_codes(session, body)
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
    await _validate_dict_codes(session, body)
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
    valid_codes = set((await session.execute(select(VulnType.code))).scalars().all())
    for i, item in enumerate(body.items, start=1):
        if item.vul_type not in valid_codes:
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
    request: Request,
    operator: User = Depends(require_perm("vuln:manage")),
    session: AsyncSession = Depends(get_session),
):
    """批量删除：按 ID 列表删除，忽略不存在的 ID。"""
    result = await session.execute(
        sa_delete(KnowledgeEntry).where(KnowledgeEntry.id.in_(body.ids))
    )
    await session.commit()
    await audit(session, request, "knowledge_delete", operator, {
        "op": "batch", "count": result.rowcount, "ids": body.ids[:50],
    })
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
    entry.cvss_vector = vul.cvss_vector or ""
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
