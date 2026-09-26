"""通用查询辅助：统一分页与「取不到即 404」，消除各路由的重复样板。"""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def paginate(session: AsyncSession, stmt, page: int, size: int):
    """对已构造好过滤/排序的 select 语句执行分页，返回 (total, items)。

    count 由传入语句去除排序后派生，避免调用方重复维护 count 条件。
    """
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await session.execute(count_stmt)).scalar_one()
    rows = (
        await session.execute(stmt.offset((page - 1) * size).limit(size))
    ).scalars().all()
    return total, rows


async def paginate_cursor(
    session: AsyncSession, stmt, *, page: int, size: int, cursor: str = "", id_col=None,
):
    """分页 + 稳定游标（P1-6），返回 `(total, rows, meta)`。

    - `cursor` 为空：沿用既有 offset 分页（`page`/`size`），`total` 为全量条数；
    - `cursor` 非空（上一页末条 id）：忽略 `page`，改按 **id 降序**稳定遍历下一页，
      `total` 仍为全量条数；
    - `meta` 含 `page`/`size`/`has_more`/`next_cursor`，`next_cursor` 为 None 表示已到末页。

    注意：游标模式强制按 id 降序，与默认业务排序（如接收日期倒序）可能不同——
    这是稳定性优先的取舍，调用方在文档中说明即可。
    """
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    working = stmt
    use_cursor = bool(cursor) and id_col is not None
    if use_cursor:
        working = working.order_by(None).order_by(id_col.desc())
        if str(cursor).isdigit():
            working = working.where(id_col < int(cursor))
        rows = (await session.execute(working.limit(size + 1))).scalars().all()
    else:
        rows = (
            await session.execute(working.offset((page - 1) * size).limit(size + 1))
        ).scalars().all()

    has_more = len(rows) > size
    rows = list(rows[:size])
    next_cursor = str(rows[-1].id) if (rows and has_more and use_cursor) else None
    meta = {"page": page, "size": size, "has_more": has_more, "next_cursor": next_cursor}
    return total, rows, meta


def apply_sort(stmt, model, sort: str, order: str, allowed: set[str], default_order):
    """按白名单字段排序；sort 非法则用 default_order。default_order 为排序表达式或其元组。

    合法排序追加 id 降序作稳定次序，避免同值行分页时顺序抖动。
    """
    if sort and sort in allowed:
        col = getattr(model, sort)
        col = col.desc() if order == "desc" else col.asc()
        return stmt.order_by(col, model.id.desc())
    if isinstance(default_order, (list, tuple)):
        return stmt.order_by(*default_order)
    return stmt.order_by(default_order)


async def get_or_404(session: AsyncSession, model, pk, detail: str = "资源不存在"):
    """按主键获取实体，不存在则抛出 404。"""
    obj = await session.get(model, pk)
    if obj is None:
        raise HTTPException(404, detail)
    return obj


async def delete_by_id_if_exists(session: AsyncSession, model, pk) -> bool:
    """按主键删除实体（**幂等**：不存在时返回 False 而不报错）。

    不负责 commit，由调用方决定提交时机；用于「删除成功」语义的删除端点，
    避免各路由重复 get → if → delete 样板。
    """
    obj = await session.get(model, pk)
    if obj is None:
        return False
    await session.delete(obj)
    return True


def parse_int_list(raw: str) -> list[int] | None:
    """逗号分隔字符串转 int 列表；空 / 全空 → None（等价不筛选）。"""
    return [int(x) for x in raw.split(",") if x.strip().isdigit()] or None


def parse_str_list(raw: str) -> list[str] | None:
    """逗号分隔字符串转 str 列表；空 / 全空 → None（等价不筛选）。"""
    return [x.strip() for x in raw.split(",") if x.strip()] or None
