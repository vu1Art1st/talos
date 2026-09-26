"""工单ID分配与唯一性校验：测试计划与漏扫基线工单共享同一当日序号序列。"""
import re

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NonpenPlan, TestingPlan, TicketSeqCounter

_PLAN_MODELS = (TestingPlan, NonpenPlan)


def _conflict_error(exc: IntegrityError) -> HTTPException:
    """约束冲突 → 409：显示编号唯一索引冲突给出可操作提示，其余归为通用数据冲突。"""
    if "ticket_no" in str(getattr(exc, "orig", "") or ""):
        return HTTPException(409, "工单ID已被占用，请更换后保存")
    return HTTPException(409, "数据冲突，请刷新后重试")


async def flush_or_conflict(session: AsyncSession) -> None:
    """flush 阶段的约束冲突同样转 409（写入中途 `session.flush()` 也会撞上唯一索引）。"""
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise _conflict_error(exc) from exc


async def commit_or_conflict(session: AsyncSession) -> None:
    """提交事务，并把数据库约束冲突（IntegrityError）统一转成 409。

    原因（P0-2）：请求前的 `check_ticket_id_unique` 只覆盖「提交前已可见」的占用，
    两个并发请求可以同时通过校验；此时唯一的兜底是 `testing_plans` / `nonpen_plans` 上的
    显示编号唯一索引。若不做转换，该冲突会以 500 暴露给用户。
    """
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _conflict_error(exc) from exc


async def _max_occupied_seq(session: AsyncSession, date_key: str, exclude_id: int | None) -> int:
    """当日**已占用**的最大序号（两表合计）。

    占用口径与显示编号一致：纯自动记录（`ticket_id_manual` 为空）的 `ticket_seq`，
    以及手动指定编号（`YYYYMMDD-N` 且日期为当日）解析出的 N，均计入；
    手动指定了编号的记录其底层 `ticket_seq` 不再视为占用（避免幽灵占用）。
    """
    date_like = f"{date_key}%"
    max_seq = 0
    for model in _PLAN_MODELS:
        stmt = select(model.ticket_seq, model.ticket_id_manual).where(
            model.receive_time.like(date_like)
        )
        if exclude_id is not None:
            stmt = stmt.where(model.id != exclude_id)
        for seq, manual in (await session.execute(stmt)).all():
            if seq and not (manual or ""):
                max_seq = max(max_seq, seq)
            m = re.fullmatch(r"(\d{8})-(\d+)", manual or "")
            if m and f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}" == date_key:
                max_seq = max(max_seq, int(m.group(2)))
    return max_seq


async def assign_ticket_seq(session: AsyncSession, row) -> None:
    """按需求接收日期为测试计划/漏扫基线工单分配当日「最大编号+1」的录入次序（ticket_seq）。

    - 两表共享同一序号序列：同一接收日期内，测试计划与漏扫基线工单合计序号连续递增；
      混合工单（勾选创建漏扫基线工单）由调用方把同一序号写入两条记录，此处只负责分配一次。
    - **并发安全（P0-2）**：序号由 `ticket_seq_counters` 单行计数器分配，
      `INSERT ... ON CONFLICT (receive_date) DO UPDATE SET last_seq = GREATEST(last_seq + 1, seed + 1)
      RETURNING last_seq` 一条语句完成「行锁 + 自增 + 取值」——同日并发创建会被数据库串行化，
      不会出现两个请求读到同一最大值而分配到重号；`GREATEST` 同时覆盖「计数器因删除/回滚落后于
      实际数据」的场景（seed 为两表当日已占用最大值），保证分配**原子且单调**。
    - 删除/释放的历史编号不复用（自动分配仅单调递增），如需使用可手动指定，
      手动编号真实未被占用时由唯一性校验 + 数据库唯一索引放行。
    - 新对象 ticket_seq 为 None（SQLAlchemy default 在构造时不生效），
      需用 falsy 判断（None/0 均视为未分配）。
    - 仅当对象已持久化（更新场景）时才排除自身，避免新对象 id 为 None 时
      生成 `id != NULL` 恒为假的 SQL 条件导致序号始终为 1。
    - 手动指定了工单ID时不自动分配序号，避免浪费当日序号。
    """
    receive_time = getattr(row, "receive_time", "")
    if not receive_time or getattr(row, "ticket_seq", None) or getattr(row, "ticket_id_manual", ""):
        return
    date_key = receive_time[:10]
    seed = await _max_occupied_seq(session, date_key, getattr(row, "id", None))
    stmt = (
        pg_insert(TicketSeqCounter)
        .values(receive_date=date_key, last_seq=seed + 1)
        .on_conflict_do_update(
            index_elements=[TicketSeqCounter.receive_date],
            set_={"last_seq": func.greatest(TicketSeqCounter.last_seq + 1, seed + 1)},
        )
        .returning(TicketSeqCounter.last_seq)
    )
    row.ticket_seq = int((await session.execute(stmt)).scalar_one())


async def check_ticket_id_unique(
    session: AsyncSession, ticket_id: str,
    exclude: list[tuple] | tuple | None = None,
) -> None:
    """校验工单ID在测试计划与漏扫基线工单两表中全局唯一。

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
