"""个人访问令牌（PAT）管理（F6）：登录用户创建/查看/吊销自己的令牌。

明文令牌仅创建响应返回一次，库中只存 sha256；开放 API 认证见 core/deps.get_pat_user。
"""
import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.query import paginate
from app.core.timeutil import now
from app.db import get_session
from app.models import PersonalAccessToken, User
from app.schemas import Page, PatCreateIn, PatCreatedOut, PatOut
from app.services.audit_service import audit

router = APIRouter(prefix="/pats", tags=["个人访问令牌"])

# 令牌明文前缀：认证侧据此区分 PAT 与 JWT
PAT_PREFIX = "tlp_"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_pat() -> tuple[str, str, str]:
    """生成 (明文令牌, sha256 hash, 展示前缀)。"""
    token = PAT_PREFIX + secrets.token_urlsafe(32)
    return token, _hash_token(token), token[:12]


@router.get("", response_model=Page[PatOut])
async def list_pats(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(PersonalAccessToken)
        .where(PersonalAccessToken.user_id == user.id)
        .order_by(PersonalAccessToken.id.desc())
    )
    total, items = await paginate(session, stmt, page, size)
    return Page(total=total, items=[PatOut.model_validate(i) for i in items])


@router.post("", response_model=PatCreatedOut)
async def create_pat(
    body: PatCreateIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from datetime import timedelta

    count = (
        await session.execute(
            select(PersonalAccessToken.id)
            .where(PersonalAccessToken.user_id == user.id, PersonalAccessToken.is_active.is_(True))
        )
    ).scalars().all()
    if len(count) >= 20:
        raise HTTPException(400, "每个用户最多保留 20 个有效令牌，请先吊销不再使用的令牌")
    token, token_hash, prefix = generate_pat()
    row = PersonalAccessToken(
        user_id=user.id,
        name=body.name.strip(),
        token_hash=token_hash,
        prefix=prefix,
        expires_at=now() + timedelta(days=body.expire_days),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    await audit(session, request, "pat_create", user, {"target": f"pats/{row.id}", "name": row.name})
    return PatCreatedOut(**PatOut.model_validate(row).model_dump(), token=token)


@router.delete("/{pat_id}")
async def revoke_pat(
    pat_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(PersonalAccessToken, pat_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "令牌不存在")
    await session.delete(row)
    await session.commit()
    await audit(session, request, "pat_revoke", user, {"target": f"pats/{pat_id}", "name": row.name})
    return {"msg": "已吊销"}
