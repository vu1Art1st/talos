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


def parse_int_list(raw: str) -> list[int] | None:
    """逗号分隔字符串转 int 列表；空 / 全空 → None（等价不筛选）。"""
    return [int(x) for x in raw.split(",") if x.strip().isdigit()] or None


def parse_str_list(raw: str) -> list[str] | None:
    """逗号分隔字符串转 str 列表；空 / 全空 → None（等价不筛选）。"""
    return [x.strip() for x in raw.split(",") if x.strip()] or None
