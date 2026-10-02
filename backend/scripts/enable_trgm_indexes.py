"""启用 pg_trgm 前后通配符索引（P0-4 评估落地，P2-4 扩展字段，显式运维动作）。

**评估结论**（2026-09-26，本机 PostgreSQL 16 + 10 万漏洞基准，见 `scripts/benchmark_lists.py --trgm`）：

| 指标 | 无 trgm 索引 | 建 GIN 三元组索引后 |
|---|---|---|
| `title ILIKE '%SQL注入%'` P95 | 43.5 ms | 5.3 ms |
| 执行计划 | Seq Scan + Filter | Bitmap Index Scan on ix_trgm_vulns_title |

**为什么不写成 Alembic 迁移**：`CREATE EXTENSION pg_trgm` 需要超级用户；写进迁移会在
「扩展不可用 / 权限不足」的库上直接让 `upgrade head` 失败（升级被一个性能优化阻断），
而全新库是 `create_all` 建的（不走迁移）会漏建索引——两条路径无法保持一致。故改为**显式、
可重入**的运维脚本：先报告可用性，再按结果决定是否建索引，最后打印 EXPLAIN 证据。

覆盖的列与两类 `%keyword%` 检索对应：
1. 全局搜索：漏洞标题 / 影响 URL、资产名称 / 子系统、渗透 / 漏扫工单计划名与测试系统、
   报告标题 / 项目名 / 章节标题 / 章节正文；
2. 图片鉴权引用查询（`api/images.py` 的 `IMAGE_REFERENCE_COLUMNS`，批次 E-1.1）：漏洞、
   导入记录与知识库条目各富文本列——图片名是 32 位十六进制串，前导通配无索引即全表扫描。
3. 审计检索（`api/v1/audit.py`）：`operation_logs` 的用户名 / IP / 详情三列（批次 E-1.4）。
4. 函数 / 类型转换后再模糊匹配的列（批次 E-1.5）：工单的「日期去横线」「序号转文本」「二者拼接」
   与资产的 JSON 转文本。PostgreSQL 只在**索引表达式与查询表达式形状一致**时才会使用，
   故这些条目必须与 `plan_query` / `assets.py` 里 SQLAlchemy 生成的表达式逐字对应。

用法（生产/本地均可在容器或本机执行；幂等，可重复运行）：

    backend/.venv/Scripts/python -m scripts.enable_trgm_indexes --dry-run
    backend/.venv/Scripts/python -m scripts.enable_trgm_indexes

输出以 `RESULT` 开头，便于筛选（见 docs/SCRIPTS.md）。
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))
os.environ.setdefault("VP_DEBUG", "1")
os.environ.setdefault("VP_DISABLE_QUEUE", "1")
os.environ.setdefault("VP_DISABLE_REDIS", "1")

from sqlalchemy import text  # noqa: E402

from app.db import async_session_maker, engine  # noqa: E402

# (索引名, 表名, 目标)：目标可以是列名，也可以是 SQL 表达式（两种都会原样写进 gin(...)）。
TRGM_INDEXES = (
    ("ix_trgm_vulns_title", "vulns", "title"),
    ("ix_trgm_vulns_affected_url", "vulns", "affected_url"),
    ("ix_trgm_assets_name", "assets", "name"),
    ("ix_trgm_assets_sub_system", "assets", "sub_system"),
    ("ix_trgm_testing_plans_system_name", "testing_plans", "system_name"),
    ("ix_trgm_testing_plans_plan_name", "testing_plans", "plan_name"),
    ("ix_trgm_nonpen_plans_system_name", "nonpen_plans", "system_name"),
    ("ix_trgm_nonpen_plans_plan_name", "nonpen_plans", "plan_name"),
    ("ix_trgm_reports_title", "reports", "title"),
    ("ix_trgm_reports_project_name", "reports", "project_name"),
    ("ix_trgm_report_sections_title", "report_sections", "title"),
    ("ix_trgm_report_sections_content_html", "report_sections", "content_html"),
    # 图片鉴权引用列（api/images.py 的 IMAGE_REFERENCE_COLUMNS）：与上面的列表检索列同属
    # 前导通配场景，缺一个就会让图片请求在该表上退化全表扫描；两者一致性由
    # tests/test_image_reference_indexes.py 守卫。
    ("ix_trgm_vulns_description_html", "vulns", "description_html"),
    ("ix_trgm_vulns_reproduce_html", "vulns", "reproduce_html"),
    ("ix_trgm_vulns_solution_html", "vulns", "solution_html"),
    ("ix_trgm_vulns_retest_html", "vulns", "retest_html"),
    ("ix_trgm_import_records_description_html", "import_records", "description_html"),
    ("ix_trgm_import_records_reproduce_html", "import_records", "reproduce_html"),
    ("ix_trgm_import_records_solution_html", "import_records", "solution_html"),
    ("ix_trgm_import_records_retest_html", "import_records", "retest_html"),
    ("ix_trgm_knowledge_entries_description_html", "knowledge_entries", "description_html"),
    ("ix_trgm_knowledge_entries_harm_html", "knowledge_entries", "harm_html"),
    ("ix_trgm_knowledge_entries_solution_html", "knowledge_entries", "solution_html"),
    # 审计检索列（api/v1/audit.py 对 username / ip / detail 各有一处 ilike '%kw%'）
    ("ix_trgm_operation_logs_username", "operation_logs", "username"),
    ("ix_trgm_operation_logs_ip", "operation_logs", "ip"),
    ("ix_trgm_operation_logs_detail", "operation_logs", "detail"),
    # ---- E-1.5：plan_query 的工单检索（plan_name / system_name 已在上面）----
    ("ix_trgm_testing_plans_department", "testing_plans", "department"),
    ("ix_trgm_testing_plans_test_type", "testing_plans", "test_type"),
    ("ix_trgm_testing_plans_ticket_id_manual", "testing_plans", "ticket_id_manual"),
    ("ix_trgm_testing_plans_receive_time", "testing_plans", "receive_time"),
    ("ix_trgm_testing_plans_receive_time_nodash", "testing_plans", "replace(receive_time, '-', '')"),
    ("ix_trgm_testing_plans_ticket_seq_text", "testing_plans", "CAST(ticket_seq AS VARCHAR)"),
    ("ix_trgm_testing_plans_auto_ticket", "testing_plans",
     "replace(receive_time, '-', '') || '-' || CAST(ticket_seq AS VARCHAR)"),
    ("ix_trgm_nonpen_plans_department", "nonpen_plans", "department"),
    ("ix_trgm_nonpen_plans_ticket_id_manual", "nonpen_plans", "ticket_id_manual"),
    ("ix_trgm_nonpen_plans_receive_time", "nonpen_plans", "receive_time"),
    ("ix_trgm_nonpen_plans_receive_time_nodash", "nonpen_plans", "replace(receive_time, '-', '')"),
    ("ix_trgm_nonpen_plans_ticket_seq_text", "nonpen_plans", "CAST(ticket_seq AS VARCHAR)"),
    ("ix_trgm_nonpen_plans_auto_ticket", "nonpen_plans",
     "replace(receive_time, '-', '') || '-' || CAST(ticket_seq AS VARCHAR)"),
    # ---- E-1.5：assets.py 的 JSON 数组转文本后模糊匹配 ----
    ("ix_trgm_assets_public_urls_text", "assets", "CAST(public_urls AS VARCHAR)"),
    ("ix_trgm_assets_internal_urls_text", "assets", "CAST(internal_urls AS VARCHAR)"),
)


async def _trgm_available() -> bool:
    async with async_session_maker() as session:
        return bool((await session.execute(text(
            "SELECT count(*) FROM pg_available_extensions WHERE name = 'pg_trgm'"
        ))).scalar_one())


async def _ensure_extension() -> bool:
    try:
        async with async_session_maker() as session:
            await session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await session.commit()
        return True
    except Exception as exc:  # noqa: BLE001  权限不足时给出结论，不抛栈
        print(f"RESULT extension=failed（需要超级用户或预装扩展）：{type(exc).__name__}")
        return False


async def _existing_indexes() -> set[str]:
    async with async_session_maker() as session:
        rows = (await session.execute(text(
            "SELECT indexname FROM pg_indexes WHERE indexname LIKE 'ix_trgm_%'"
        ))).all()
        return {r[0] for r in rows}


async def _create_indexes(dry_run: bool) -> int:
    before = await _existing_indexes()
    created = 0
    async with async_session_maker() as session:
        for name, table, column in TRGM_INDEXES:
            if name in before:
                print(f"RESULT index={name} status=exists")
                continue
            if dry_run:
                print(f"RESULT index={name} status=would-create on {table}({column})")
                continue
            await session.execute(text(
                # 目标统一加一层括号：纯列名合法，复合表达式（如 `a || '-' || b`）也才不会被
                # 解析成 `... || (b gin_trgm_ops)`。
                f"CREATE INDEX IF NOT EXISTS {name} ON {table} USING gin (({column}) gin_trgm_ops)"
            ))
            print(f"RESULT index={name} status=created on {table}({column})")
            created += 1
        if not dry_run:
            await session.commit()
    return created


async def main() -> None:
    parser = argparse.ArgumentParser(description="启用 pg_trgm 前后通配符索引（幂等）")
    parser.add_argument("--dry-run", action="store_true", help="只报告将执行的动作")
    args = parser.parse_args()

    if not await _trgm_available():
        print("RESULT trgm=unavailable（当前 PostgreSQL 未提供 pg_trgm，脚本无操作）")
        return
    print("RESULT trgm=available")
    if not args.dry_run and not await _ensure_extension():
        return
    created = await _create_indexes(args.dry_run)
    if not args.dry_run:
        async with async_session_maker() as session:
            for _name, table, _column in TRGM_INDEXES:
                await session.execute(text(f"ANALYZE {table}"))
            await session.commit()
        print(f"RESULT summary=created:{created} total:{len(TRGM_INDEXES)}")
        # 自证：打印一条代表性 EXPLAIN，确认索引可用（表为空时计划可能仍选顺序扫描）
        async with async_session_maker() as session:
            rows = (await session.execute(text(
                "EXPLAIN SELECT id FROM vulns WHERE title ILIKE '%SQL%' LIMIT 20"
            ))).all()
            for row in rows:
                print(f"RESULT   {row[0]}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
