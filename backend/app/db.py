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


async def _migrate_lightweight() -> None:
    """幂等轻量迁移（SQLite 开发库）：补新增列、删除已废弃列。"""
    from sqlalchemy import text

    async with engine.begin() as conn:
        if engine.dialect.name != "sqlite":
            return
        vul_cols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(vulns)"))).fetchall()}
        legacy_plan_status = "testing_plan_id" not in vul_cols  # 本轮升级前的旧库标记
        if "retest_html" not in vul_cols:
            await conn.execute(text("ALTER TABLE vulns ADD COLUMN retest_html TEXT NOT NULL DEFAULT ''"))
        if "retest_json" not in vul_cols:
            await conn.execute(text("ALTER TABLE vulns ADD COLUMN retest_json JSON"))
        if "testing_plan_id" not in vul_cols:
            await conn.execute(text("ALTER TABLE vulns ADD COLUMN testing_plan_id INTEGER"))
        report_cols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(reports)"))).fetchall()}
        if "testing_plan_id" not in report_cols:
            await conn.execute(text("ALTER TABLE reports ADD COLUMN testing_plan_id INTEGER"))
        if "target_ip" not in report_cols:
            await conn.execute(text("ALTER TABLE reports ADD COLUMN target_ip VARCHAR(255) NOT NULL DEFAULT ''"))
        for col in ("summary_html", "summary_json"):
            if col in report_cols:
                try:
                    await conn.execute(text(f"ALTER TABLE reports DROP COLUMN {col}"))
                except Exception:  # noqa: BLE001  SQLite < 3.35 不支持 DROP COLUMN，忽略残留列
                    pass
        if legacy_plan_status:
            # 状态码语义升级（六档），仅对旧库一次性重映射：50 已完成→60 复测完成，40 复测中→50 复测中
            await conn.execute(text("UPDATE testing_plans SET status = 60 WHERE status = 50"))
            await conn.execute(text("UPDATE testing_plans SET status = 50 WHERE status = 40"))


async def init_db() -> None:
    """建表并写入初始角色与管理员（幂等）。生产环境版本化演进使用 Alembic。"""
    import app.models  # noqa: F401  确保模型全部注册

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await _migrate_lightweight()

    from sqlalchemy import select

    from app.core.security import hash_password
    from app.models import Role, User

    async with async_session_maker() as session:
        role = (await session.execute(select(Role).where(Role.name == "超级管理员"))).scalar_one_or_none()
        if role is None:
            role = Role(name="超级管理员", permissions=["*"], remark="内置角色，拥有全部权限")
            session.add(role)
            session.add(Role(name="安全工程师", permissions=[
                "dashboard:view", "asset:manage",
                "vuln:submit", "vuln:audit", "vuln:manage",
                "import:manage", "report:manage", "special:manage",
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
