"""春耕行动 API：记录 CRUD 与漏洞关联，统一 special:manage 权限。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_perm
from app.core.query import get_or_404, paginate, apply_sort
from app.db import get_session
from app.models import SpringAction, User
from app.schemas import Page, SpringActionIn, SpringActionOut
from app.services import vuln_service

router = APIRouter(tags=["专项管理"])


@router.get("/spring-actions", response_model=Page[SpringActionOut])
async def list_spring_actions(
    search: str = "",
    sort: str = "",
    order: str = "desc",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    cond = []
    if search:
        cond.append(
            SpringAction.report_no.ilike(f"%{search}%")
            | SpringAction.system_name.ilike(f"%{search}%")
            | SpringAction.doc_no.ilike(f"%{search}%")
        )
    stmt = select(SpringAction).where(*cond)
    stmt = apply_sort(
        stmt, SpringAction, sort, order,
        {"id", "report_no", "system_name", "year", "phase", "appeal_success",
         "score_deduction", "doc_no", "create_time"},
        SpringAction.id.desc(),
    )
    total, items = await paginate(session, stmt, page, size)
    return Page(total=total, items=items)


@router.post("/spring-actions", response_model=SpringActionOut)
async def create_spring_action(
    body: SpringActionIn,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = SpringAction(**body.model_dump(exclude={"vul_ids"}), creator_id=user.id)
    row.vuls = await vuln_service.load_vulns_or_400(session, body.vul_ids)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.put("/spring-actions/{row_id}", response_model=SpringActionOut)
async def update_spring_action(
    row_id: int,
    body: SpringActionIn,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await get_or_404(session, SpringAction, row_id, "春耕行动记录不存在")
    for k, v in body.model_dump(exclude={"vul_ids"}).items():
        setattr(row, k, v)
    row.vuls = await vuln_service.load_vulns_or_400(session, body.vul_ids)
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/spring-actions/{row_id}")
async def delete_spring_action(
    row_id: int,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(SpringAction, row_id)
    if row:
        await session.delete(row)
        await session.commit()
    return {"msg": "删除成功"}
