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
    from app.models import DictOption, Role, User

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
            import logging
            import secrets

            # 初始口令：优先取配置，留空则随机生成并打印（仅显示一次）
            # 仅当口令为随机生成时强制首登改密；运维显式指定则视为有意为之
            initial_pwd = settings.INITIAL_ADMIN_PASSWORD or secrets.token_urlsafe(12)
            session.add(User(
                username="admin",
                password_hash=hash_password(initial_pwd),
                realname="管理员",
                role_id=role.id,
                must_change_password=not settings.INITIAL_ADMIN_PASSWORD,
            ))
            if not settings.INITIAL_ADMIN_PASSWORD:
                logging.getLogger(__name__).warning(
                    "已创建内置 admin，初始密码（仅显示一次，首次登录必须修改）: %s", initial_pwd
                )

        # 测试计划-测试类型字典预设项（该分类为空时一次性写入）
        has_test_type = (
            await session.execute(
                select(DictOption.id).where(DictOption.category == "test_type").limit(1)
            )
        ).scalar_one_or_none()
        if has_test_type is None:
            presets = ["加电上线", "互联网自主测试", "办公网自主测试", "CHBN项目测试", "品质测评"]
            for i, name in enumerate(presets):
                session.add(DictOption(category="test_type", name=name, sort=i))

        # 资产系统类型字典预置（该分类为空时一次性写入）
        has_system_type = (
            await session.execute(
                select(DictOption.id).where(DictOption.category == "system_type").limit(1)
            )
        ).scalar_one_or_none()
        if has_system_type is None:
            for i, name in enumerate(["自有系统（正式）", "自有系统（测试）", "DICT系统"]):
                session.add(DictOption(category="system_type", name=name, sort=i))

        # 漏洞类型字典预置（表为空时从 VUL_TYPE 常量一次性写入内置类型）
        from app.models import VulnType
        has_vuln_type = (
            await session.execute(select(VulnType.id).limit(1))
        ).scalar_one_or_none()
        if has_vuln_type is None:
            from app.constants import VUL_TYPE
            for i, (code, name) in enumerate(sorted(VUL_TYPE.items())):
                session.add(VulnType(code=code, name=name, sort=i, is_builtin=True))
        await session.commit()
