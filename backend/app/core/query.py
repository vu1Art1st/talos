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


async def get_or_404(session: AsyncSession, model, pk, detail: str = "资源不存在"):
    """按主键获取实体，不存在则抛出 404。"""
    obj = await session.get(model, pk)
    if obj is None:
        raise HTTPException(404, detail)
    return obj
