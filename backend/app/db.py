from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG, pool_pre_ping=True)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def init_db() -> None:
    """建表并写入初始角色与管理员（幂等）。生产环境版本化演进使用 Alembic。"""
    import app.models  # noqa: F401  确保模型全部注册

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from sqlalchemy import select

    from app.core.security import hash_password
    from app.models import Role, User

    async with async_session_maker() as session:
        role = (await session.execute(select(Role).where(Role.name == "超级管理员"))).scalar_one_or_none()
        if role is None:
            role = Role(name="超级管理员", permissions=["*"], remark="内置角色，拥有全部权限")
            session.add(role)
            session.add(Role(name="安全工程师", permissions=[
                "dashboard:view", "app:manage", "asset:manage",
                "vuln:submit", "vuln:audit", "vuln:manage",
                "import:manage", "report:manage",
            ], remark="内置角色"))
            session.add(Role(name="研发人员", permissions=["dashboard:view", "vuln:submit"], remark="内置角色"))
            await session.flush()

        user = (await session.execute(select(User).where(User.username == "admin"))).scalar_one_or_none()
        if user is None:
            session.add(User(
                username="admin",
                password_hash=hash_password("admin123"),
                realname="管理员",
                role_id=role.id,
            ))
        await session.commit()
