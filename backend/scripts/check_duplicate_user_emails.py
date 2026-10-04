"""升级前检查用户邮箱重复：有重复时退出码 1，并输出用户名清单。"""
import asyncio

from sqlalchemy import func, select

from app.core.identity import normalize_email
from app.db import async_session_maker
from app.models import User


async def run() -> int:
    async with async_session_maker() as session:
        rows = (
            await session.execute(
                select(func.lower(User.email), func.count(User.id))
                .where(User.email != "")
                .group_by(func.lower(User.email))
                .having(func.count(User.id) > 1)
                .order_by(func.lower(User.email))
            )
        ).all()
        if not rows:
            print("[email-check] 未发现重复用户邮箱")
            return 0
        print(f"[email-check] 发现 {len(rows)} 组重复邮箱：")
        for email, count in rows:
            users = (
                await session.execute(
                    select(User.username).where(func.lower(User.email) == normalize_email(email))
                )
            ).scalars().all()
            print(f"  - {email} ({count}): {', '.join(users)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
