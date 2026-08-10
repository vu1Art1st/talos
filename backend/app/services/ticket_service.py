"""工单ID分配与唯一性校验：测试计划与非渗透计划共享同一当日序号序列。"""
import re

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NonpenPlan, TestingPlan

_PLAN_MODELS = (TestingPlan, NonpenPlan)


async def assign_ticket_seq(session: AsyncSession, row) -> None:
    """按需求接收日期为测试计划/非渗透计划分配当日「最大编号+1」的录入次序（ticket_seq）。

    - 两表共享同一序号序列：同一接收日期内，测试计划与非渗透计划合计序号连续递增；
      混合工单（勾选创建非渗透）由调用方把同一序号写入两条记录，此处只负责分配一次。
    - 占用口径与显示编号一致：纯自动记录（ticket_id_manual 为空）的 ticket_seq，
      以及手动指定编号（YYYYMMDD-N 且日期为当日）解析出的 N，均计入最大编号；
      新序号 = 最大编号 + 1，保证单调递增且不与任何占用冲突（含手动指定）。
    - 删除/释放的历史编号不复用（自动分配仅单调递增），如需使用可手动指定，
      手动编号真实未被占用时由唯一性校验放行。
    - 新对象 ticket_seq 为 None（SQLAlchemy default 在构造时不生效），
      需用 falsy 判断（None/0 均视为未分配）。
    - 仅当对象已持久化（更新场景）时才排除自身，避免新对象 id 为 None 时
      生成 `id != NULL` 恒为假的 SQL 条件导致序号始终为 1。
    - 手动指定了工单ID时不自动分配序号，避免浪费当日序号。
    """
    receive_time = getattr(row, "receive_time", "")
    if not receive_time or getattr(row, "ticket_seq", None) or getattr(row, "ticket_id_manual", ""):
        return
    date_like = f"{receive_time[:10]}%"
    max_seq = 0
    for model in _PLAN_MODELS:
        stmt = select(model.ticket_seq, model.ticket_id_manual).where(
            model.receive_time.like(date_like)
        )
        if row.id is not None:
            stmt = stmt.where(model.id != row.id)
        for seq, manual in (await session.execute(stmt)).all():
            if seq:
                max_seq = max(max_seq, seq)
            m = re.fullmatch(r"(\d{8})-(\d+)", manual or "")
            if m and f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}" == receive_time[:10]:
                max_seq = max(max_seq, int(m.group(2)))
    row.ticket_seq = max_seq + 1


async def check_ticket_id_unique(
    session: AsyncSession, ticket_id: str,
    exclude: list[tuple] | tuple | None = None,
) -> None:
    """校验工单ID在测试计划与非渗透计划两表中全局唯一。

    exclude: (model, id) 或 [(model, id), ...]，编辑场景排除自身及联动记录
    （联动双方共享同一工单ID，需相互排除）。
    口径与「显示编号」一致——手动指定值本身，或纯自动记录（ticket_id_manual 为空）
    由 receive_time+ticket_seq 生成的值，均不得与其他记录重复。
    手动指定了编号的记录其底层 ticket_seq 不再视为占用（避免幽灵占用——
    如先自动生成 20260730-3 后手动改为 20260730-88 时，20260730-3 仍可被手动使用）。
    """
    if not ticket_id:
        return
    if isinstance(exclude, tuple):
        exclusions = [exclude]
    else:
        exclusions = exclude or []
    m = re.fullmatch(r"(\d{8})-(\d+)", ticket_id)
    date_like = None
    if m:
        date_part = m.group(1)
        date_like = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:]}%"
    for model in _PLAN_MODELS:
        conds = [model.ticket_id_manual == ticket_id]
        if date_like:
            conds.append(and_(
                model.receive_time.like(date_like),
                model.ticket_seq == int(m.group(2)),
                model.ticket_id_manual == "",
            ))
        stmt = select(model.id).where(or_(*conds))
        for excl_model, excl_id in exclusions:
            if excl_model is model:
                stmt = stmt.where(model.id != excl_id)
        if (await session.execute(stmt)).first() is not None:
            raise HTTPException(400, f"工单ID「{ticket_id}」已存在，请更换后保存")
