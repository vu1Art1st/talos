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
        user_cols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(users)"))).fetchall()}
        if user_cols and "token_version" not in user_cols:
            await conn.execute(text("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"))
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
        if report_cols and "revision" not in report_cols:
            await conn.execute(text("ALTER TABLE reports ADD COLUMN revision INTEGER NOT NULL DEFAULT 0"))
        plan_cols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(testing_plans)"))).fetchall()}
        if plan_cols and "est_mandays" not in plan_cols:
            await conn.execute(text("ALTER TABLE testing_plans ADD COLUMN est_mandays REAL NOT NULL DEFAULT 0"))
        if plan_cols and "actual_mandays" not in plan_cols:
            await conn.execute(text("ALTER TABLE testing_plans ADD COLUMN actual_mandays REAL NOT NULL DEFAULT 0"))
        # 测试计划增强字段：工单时间/工单序号/计划名称/手动工单ID/关联资产
        for col, ddl in (
            ("ticket_time", "VARCHAR(32) NOT NULL DEFAULT ''"),
            ("ticket_seq", "INTEGER NOT NULL DEFAULT 0"),
            ("plan_name", "VARCHAR(128) NOT NULL DEFAULT ''"),
            ("ticket_id_manual", "VARCHAR(64) NOT NULL DEFAULT ''"),
        ):
            if plan_cols and col not in plan_cols:
                await conn.execute(text(f"ALTER TABLE testing_plans ADD COLUMN {col} {ddl}"))
        if plan_cols and "asset_ids" not in plan_cols:
            await conn.execute(text("ALTER TABLE testing_plans ADD COLUMN asset_ids JSON"))
        # 存量资产关联为空时回填空数组（幂等），避免 NULL 导致 TestingPlanOut 序列化 500
        await conn.execute(text("UPDATE testing_plans SET asset_ids = '[]' WHERE asset_ids IS NULL"))
        export_cols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(export_jobs)"))).fetchall()}
        if export_cols and "title" not in export_cols:
            await conn.execute(text("ALTER TABLE export_jobs ADD COLUMN title VARCHAR(255) NOT NULL DEFAULT ''"))
        if export_cols and "toc_auto_updated" not in export_cols:
            await conn.execute(
                text("ALTER TABLE export_jobs ADD COLUMN toc_auto_updated BOOLEAN NOT NULL DEFAULT 0")
            )
        spring_cols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(spring_actions)"))).fetchall()}
        if spring_cols and "year" not in spring_cols:
            await conn.execute(text("ALTER TABLE spring_actions ADD COLUMN year VARCHAR(8) NOT NULL DEFAULT ''"))
        if spring_cols and "phase" not in spring_cols:
            await conn.execute(text("ALTER TABLE spring_actions ADD COLUMN phase VARCHAR(64) NOT NULL DEFAULT ''"))
        batch_cols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(import_batches)"))).fetchall()}
        if batch_cols and "doc_kind" not in batch_cols:
            await conn.execute(text("ALTER TABLE import_batches ADD COLUMN doc_kind VARCHAR(16) NOT NULL DEFAULT 'template'"))
        if batch_cols and "meta_json" not in batch_cols:
            await conn.execute(text("ALTER TABLE import_batches ADD COLUMN meta_json JSON"))
        record_cols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(import_records)"))).fetchall()}
        if record_cols and "retest_html" not in record_cols:
            await conn.execute(text("ALTER TABLE import_records ADD COLUMN retest_html TEXT NOT NULL DEFAULT ''"))
        if record_cols and "fixed" not in record_cols:
            await conn.execute(text("ALTER TABLE import_records ADD COLUMN fixed BOOLEAN NOT NULL DEFAULT 0"))
        # 组织新增系统负责人三字段
        group_cols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(groups)"))).fetchall()}
        for col, ddl in (("owner_name", "VARCHAR(64)"), ("owner_phone", "VARCHAR(32)"), ("owner_email", "VARCHAR(128)")):
            if group_cols and col not in group_cols:
                await conn.execute(text(f"ALTER TABLE groups ADD COLUMN {col} {ddl} NOT NULL DEFAULT ''"))
        # 资产技术信息结构化：端口与服务成对、中间件/数据库多条目带版本
        asset_cols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(assets)"))).fetchall()}
        for col in ("port_services", "middlewares", "databases"):
            if asset_cols and col not in asset_cols:
                await conn.execute(text(f"ALTER TABLE assets ADD COLUMN {col} JSON"))
        # 资产系统类型字段
        if asset_cols and "system_type" not in asset_cols:
            await conn.execute(text("ALTER TABLE assets ADD COLUMN system_type VARCHAR(64) NOT NULL DEFAULT ''"))
        # 知识库新增漏洞名称/危害等级：唯一键从漏洞类型迁至漏洞名称（同类型可多条）
        kb_cols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(knowledge_entries)"))).fetchall()}
        if kb_cols and "vulnerability_name" not in kb_cols:
            from app.constants import VUL_TYPE

            await conn.execute(text(
                "ALTER TABLE knowledge_entries ADD COLUMN vulnerability_name VARCHAR(255) NOT NULL DEFAULT ''"
            ))
            await conn.execute(text(
                "ALTER TABLE knowledge_entries ADD COLUMN severity_level INTEGER NOT NULL DEFAULT 30"
            ))
            # 存量行名称回填为类型名（旧库 vul_type 唯一，回填后名称不重复）
            for code, name in VUL_TYPE.items():
                await conn.execute(
                    text("UPDATE knowledge_entries SET vulnerability_name = :name "
                         "WHERE vul_type = :code AND vulnerability_name = ''"),
                    {"name": name, "code": code},
                )
            await conn.execute(text("DROP INDEX IF EXISTS ix_knowledge_entries_vul_type"))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_knowledge_entries_vul_type ON knowledge_entries (vul_type)"
            ))
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_knowledge_entries_vulnerability_name "
                "ON knowledge_entries (vulnerability_name)"
            ))
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
        # 复测轮次表为空时，为已进入复测阶段的存量计划回填第 1 轮记录（幂等）
        round_count = (
            await conn.execute(text("SELECT COUNT(*) FROM testing_plan_retest_rounds"))
        ).scalar_one()
        if round_count == 0:
            await conn.execute(text(
                "INSERT INTO testing_plan_retest_rounds (plan_id, round_no, start_time, done_time, source) "
                "SELECT id, 1, CURRENT_TIMESTAMP, "
                "CASE WHEN status = 60 THEN CURRENT_TIMESTAMP ELSE NULL END, '历史数据回填' "
                "FROM testing_plans WHERE status >= 50 OR retest_done_time != ''"
            ))
        # 复测报告导入遗留修复：计划错误停留"复测完成"但仍有未闭环漏洞（幂等，先修漏洞后修计划）
        await conn.execute(text(
            "UPDATE vulns SET status = 55, is_retest = 1 "
            "WHERE source = 60 AND status = 10 "
            "AND testing_plan_id IN (SELECT id FROM testing_plans WHERE status = 60) "
            "AND testing_plan_id IN ("
            "  SELECT DISTINCT testing_plan_id FROM vulns "
            "  WHERE testing_plan_id IS NOT NULL AND status NOT IN (20, 60))"
        ))
        await conn.execute(text(
            "UPDATE testing_plans SET status = 50 "
            "WHERE status = 60 AND id IN ("
            "  SELECT DISTINCT testing_plan_id FROM vulns "
            "  WHERE testing_plan_id IS NOT NULL AND status NOT IN (20, 60))"
        ))


async def _backfill_asset_tech_fields() -> None:
    """历史技术字段一次性回填（幂等）：ports/services/middleware/database_type → 新 JSON 字段。"""
    import re

    from sqlalchemy import select

    from app.models import Asset

    def _split(text_: str) -> list[str]:
        return [p for p in (s.strip() for s in re.split(r"[;；/、,，]", text_ or "")) if p]

    async with async_session_maker() as session:
        assets = (await session.execute(select(Asset))).scalars().all()
        changed = False
        for a in assets:
            # 新增列对存量行为 NULL，归一化为空列表，避免序列化校验失败
            for col in ("port_services", "middlewares", "databases"):
                if getattr(a, col) is None:
                    setattr(a, col, [])
                    changed = True
            if not a.port_services and (a.ports or a.services):
                pairs = [{"port": p, "service": ""} for p in (a.ports or [])]
                if a.services:
                    if pairs:
                        pairs[0]["service"] = a.services
                    else:
                        pairs = [{"port": "", "service": a.services}]
                a.port_services = pairs
                changed = True
            if not a.middlewares and a.middleware:
                a.middlewares = [{"name": n, "version": ""} for n in _split(a.middleware)]
                changed = True
            if not a.databases and a.database_type:
                a.databases = [{"name": n, "version": ""} for n in _split(a.database_type)]
                changed = True
        if changed:
            await session.commit()


async def init_db() -> None:
    """建表并写入初始角色与管理员（幂等）。生产环境版本化演进使用 Alembic。"""
    import app.models  # noqa: F401  确保模型全部注册

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await _migrate_lightweight()
    await _backfill_asset_tech_fields()

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
            for i, name in enumerate(["自有系统（正式）", "自有系统（测试）", "DCIT系统"]):
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
