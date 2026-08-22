from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_perm
from app.db import get_session
from app.models import User
from app.services.stats_service import build_stats

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats")
async def stats(
    date_from: str = "",
    date_to: str = "",
    department: str = "",
    source: int | None = None,
    level: int | None = None,
    _: User = Depends(require_perm("dashboard:view")),
    session: AsyncSession = Depends(get_session),
):
    """安全态势聚合（services/stats_service 与开放 API /open/stats 共用口径）。"""
    return await build_stats(
        session, date_from=date_from, date_to=date_to,
        department=department, source=source, level=level,
    )
