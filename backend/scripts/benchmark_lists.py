"""列表分页与热点查询性能基准（ROADMAP P0-4）。

**为什么需要**：索引与「下推到 SQL」的优化只有在**有量级的数据**上才可判定；本脚本在
独立 schema 里造出可重复的基准数据（默认 10 万漏洞 / 1 万工单 / 1 万报告 / 5 千漏扫工单），
对列表首屏的**同一条代码路径**（路由层使用的条件构造器 + `core/query.paginate`）计时，
并输出 P50 / P95 与 `EXPLAIN (ANALYZE, BUFFERS)`，用于判断回归与索引命中。

**隔离与安全**：全程使用自己创建的 schema（默认 `bench_<pid>`，可用 `VP_DB_SCHEMA` 覆盖），
结束时 DROP；不触碰 `public` 与既有数据。必须显式提供 `VP_DATABASE_URL`
（默认值指向开发库时会被拒绝，避免误在业务库上灌 10 万行）。

用法（仓库根目录，backend 解释器）：

    $env:VP_DATABASE_URL="postgresql+asyncpg://vuln:pass@127.0.0.1:5432/vulnplatform_test"
    backend/.venv/Scripts/python -m scripts.benchmark_lists --vulns 100000 --plans 10000 \
        --reports 10000 --nonpen 5000 --runs 7

输出标记以 `RESULT` 开头，便于从 SQLAlchemy echo 中筛选（见 docs/SCRIPTS.md）。
"""
import argparse
import asyncio
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

# 以下环境变量必须在导入 app.* 之前设置：app.db 的 engine 在导入时按 VP_DB_SCHEMA 固定 search_path
_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))
os.environ.setdefault("VP_DEBUG", "1")
os.environ.setdefault("VP_DISABLE_QUEUE", "1")
os.environ.setdefault("VP_DISABLE_REDIS", "1")
_SCHEMA = os.environ.setdefault("VP_DB_SCHEMA", f"bench_{os.getpid()}")

from sqlalchemy import insert, select, text  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402

from app.core.query import apply_sort, paginate  # noqa: E402
from app.core.timeutil import now as tznow  # noqa: E402
from app.db import async_session_maker, engine  # noqa: E402
from app.models import NonpenPlan, OperationLog, Report, TestingPlan, Vul  # noqa: E402
from app.services import plan_query  # noqa: E402
from app.services.nonpen_service import build_items  # noqa: E402

_CHUNK = 2000


def _pct(values: list[float], ratio: float) -> float:
    """线性插值百分位（样本量小也能给出稳定结果）。"""
    if not values:
        return 0.0
    ordered = sorted(values)
    pos = min(max(ratio, 0.0), 1.0) * (len(ordered) - 1)
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


async def _reset_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE'))
        await conn.execute(text(f'CREATE SCHEMA "{_SCHEMA}"'))
    from app.db import init_db

    await init_db()


async def _seed(vulns: int, plans: int, reports: int, nonpen: int, logs: int) -> None:
    """批量造数：Core bulk insert 分块提交，避免单条 ORM 写入的十倍开销。"""
    async with async_session_maker() as session:
        for start in range(0, plans, _CHUNK):
            rows = [
                {
                    "system_name": f"基准系统-{i}",
                    "department": f"部门-{i % 20}",
                    "test_type": "渗透测试",
                    "receive_time": f"2026-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
                    "status": 10 + (i % 5) * 10,
                    "create_time": tznow(),
                    "update_time": tznow(),
                }
                for i in range(start, min(start + _CHUNK, plans))
            ]
            await session.execute(insert(TestingPlan), rows)
        for start in range(0, nonpen, _CHUNK):
            rows = [
                {
                    "system_name": f"基准漏扫-{i}",
                    "department": f"部门-{i % 20}",
                    "receive_time": f"2026-{(i % 12) + 1:02d}-01",
                    "items": build_items(
                        ["baseline", "host"] if i % 3 else ["baseline"],
                    ),
                    "create_time": tznow(),
                    "update_time": tznow(),
                }
                for i in range(start, min(start + _CHUNK, nonpen))
            ]
            await session.execute(insert(NonpenPlan), rows)
        for start in range(0, reports, _CHUNK):
            rows = [
                {
                    "title": f"基准报告-{i}",
                    "author": "基准",
                    "create_time": tznow(),
                    "update_time": tznow(),
                }
                for i in range(start, min(start + _CHUNK, reports))
            ]
            await session.execute(insert(Report), rows)
        for start in range(0, vulns, _CHUNK):
            # 提交时间铺满最近一年：让「按天 / 按周」的时间范围筛选具备真实选择性，
            # 否则所有行同一时间戳时规划器只能全表扫描，无法验证 submit_time 索引
            rows = [
                {
                    # 关键词只出现在 1% 的行上：让 `%keyword%` 检索具备选择性，
                    # 否则规划器对「全部命中」的模糊条件只能选顺序扫描，无法评估 trgm 索引
                    "title": (
                        f"基准漏洞-{i}-SQL注入" if i % 100 == 0 else f"基准漏洞-{i}-弱口令"
                    ),
                    "vul_type": 10,
                    "level": 10 + (i % 4) * 10,
                    "status": 10 + (i % 6) * 10,
                    "submit_time": tznow() - timedelta(days=i % 365),
                    "update_time": tznow() - timedelta(days=i % 365),
                }
                for i in range(start, min(start + _CHUNK, vulns))
            ]
            await session.execute(insert(Vul), rows)
        for start in range(0, logs, _CHUNK):
            rows = [
                {"username": "admin", "action": "login", "create_time": tznow()}
                for _ in range(start, min(start + _CHUNK, logs))
            ]
            await session.execute(insert(OperationLog), rows)
        await session.commit()


# ---------- 被测查询：与路由层使用同一批条件构造器 ----------


async def _q_plan_list(session, page: int):
    """渗透测试工单列表首屏（含关键词 + 部门 + 时间范围 + 排序）。"""
    cond = plan_query.plan_conditions(
        search="基准系统", department="部门-3", receive_from="2026-01-01", receive_to="2026-12-31",
    )
    stmt = apply_sort(
        select(TestingPlan).where(*cond), TestingPlan, "receive_time", "desc", set(),
        TestingPlan.id.desc(),
    )
    return await paginate(session, stmt, page, 20)


async def _q_nonpen_actionable(session, page: int):
    """漏扫基线「仅可进行」列表（P0-4 的核心优化点）。"""
    stmt = apply_sort(
        select(NonpenPlan).where(plan_query.nonpen_actionable_condition()),
        NonpenPlan, "receive_time", "desc", set(), NonpenPlan.id.desc(),
    )
    return await paginate(session, stmt, page, 20)


async def _q_vul_list(session, page: int):
    """漏洞列表首屏（关键词模糊 + 状态 + 提交时间范围 + 排序）。"""
    stmt = select(Vul).where(
        Vul.title.ilike("%SQL注入%"),
        Vul.status == 20,
        Vul.submit_time >= tznow().replace(hour=0, minute=0, second=0, microsecond=0),
    )
    stmt = apply_sort(stmt, Vul, "submit_time", "desc", set(), Vul.id.desc())
    return await paginate(session, stmt, page, 20)


async def _q_report_list(session, page: int):
    """报告列表首屏（按更新时间排序）。"""
    stmt = apply_sort(
        select(Report), Report, "update_time", "desc", set(), Report.id.desc(),
    )
    return await paginate(session, stmt, page, 20)


async def _q_audit_list(session, page: int):
    """审计日志列表（按时间倒序）。"""
    stmt = apply_sort(
        select(OperationLog), OperationLog, "create_time", "desc", set(), OperationLog.id.desc(),
    )
    return await paginate(session, stmt, page, 20)


_QUERIES = {
    "vulns.list": _q_vul_list,
    "testing-plans.list": _q_plan_list,
    "nonpen-plans.actionable": _q_nonpen_actionable,
    "reports.list": _q_report_list,
    "audit.logs": _q_audit_list,
}


async def _measure(session, name: str, fn, runs: int) -> None:
    """跑 N 次取样（含预热）并输出 total 与 p50 / p95 / max（毫秒）。"""
    await fn(session, 1)  # 预热：含连接与计划缓存建立
    samples: list[float] = []
    total = 0
    for i in range(runs):
        started = time.perf_counter()
        total, _rows = await fn(session, 1 + i % 3)  # 轮换页码，覆盖首屏与非首屏
        samples.append((time.perf_counter() - started) * 1000)
    print(
        f"RESULT {name}: total={total} p50={_pct(samples, 0.5):.1f}ms "
        f"p95={_pct(samples, 0.95):.1f}ms max={max(samples):.1f}ms"
    )


async def _q_vul_keyword(session, page: int):
    """漏洞关键词模糊检索（`%keyword%`）：当前唯一的**前后通配符**热点路径。"""
    stmt = select(Vul).where(Vul.title.ilike("%SQL注入%"))
    stmt = apply_sort(stmt, Vul, "id", "desc", set(), Vul.id.desc())
    return await paginate(session, stmt, page, 20)


# pg_trgm 评估覆盖的「前后通配符」列（与 P0-4 评估项对应）
_TRGM_COLUMNS = (
    ("vulns", "title"), ("assets", "name"),
    ("testing_plans", "system_name"), ("nonpen_plans", "system_name"),
)


async def _enable_trgm(session) -> bool:
    """评估用：尝试启用 pg_trgm 并建 GIN 三元组索引；不可用 / 无权限时给出明确结论。

    `CREATE EXTENSION` 按 search_path 安装到本脚本的临时 schema（随 schema 一起 DROP），
    不对库内既有 schema 造成残留。
    """
    available = (await session.execute(text(
        "SELECT count(*) FROM pg_available_extensions WHERE name = 'pg_trgm'"
    ))).scalar_one()
    if not available:
        print("RESULT trgm=unavailable（当前 PostgreSQL 未提供 pg_trgm，评估跳过）")
        return False
    try:
        await session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    except Exception as exc:  # noqa: BLE001  权限不足时给出结论而不中断基准
        print(f"RESULT trgm=denied（CREATE EXTENSION 失败：{type(exc).__name__}）")
        return False
    for table, column in _TRGM_COLUMNS:
        await session.execute(text(
            f"CREATE INDEX IF NOT EXISTS ix_trgm_{table}_{column} "
            f"ON {table} USING gin ({column} gin_trgm_ops)"
        ))
    await session.commit()
    return True


async def _explain(session, name: str) -> list[str]:
    """对指定查询跑 EXPLAIN (ANALYZE, BUFFERS)，返回计划行（用于确认索引命中）。"""
    stmt = {
        "nonpen-plans.actionable": select(NonpenPlan).where(
            plan_query.nonpen_actionable_condition()
        ).order_by(NonpenPlan.id.desc()).limit(20),
        # 30 天窗口：验证 submit_time 索引在具选择性区间上被使用
        "vulns.list": select(Vul).where(
            Vul.submit_time >= tznow() - timedelta(days=30)
        ).order_by(Vul.submit_time.desc()).limit(20),
        "testing-plans.list": select(TestingPlan).where(
            TestingPlan.department == "部门-3"
        ).limit(20),
    }[name]
    sql = str(stmt.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
    ))
    rows = await session.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {sql}"))
    return [r[0] for r in rows.all()]


async def _run(args) -> None:
    import app.models  # noqa: F401  注册全部模型

    t0 = time.perf_counter()
    await _reset_schema()
    await _seed(args.vulns, args.plans, args.reports, args.nonpen, args.logs)
    print(
        f"RESULT seeded vulns={args.vulns} plans={args.plans} reports={args.reports} "
        f"nonpen={args.nonpen} logs={args.logs} in {time.perf_counter() - t0:.1f}s"
    )

    async with async_session_maker() as session:
        for name, fn in _QUERIES.items():
            await _measure(session, name, fn, args.runs)

        if args.explain:
            for name in ("nonpen-plans.actionable", "vulns.list", "testing-plans.list"):
                print(f"RESULT EXPLAIN {name}:")
                for line in await _explain(session, name):
                    print(f"RESULT   {line}")

        if args.trgm:
            await _measure(session, "vulns.keyword(before trgm)", _q_vul_keyword, args.runs)
            if await _enable_trgm(session):
                await session.execute(text("ANALYZE vulns"))
                await _measure(session, "vulns.keyword(after trgm)", _q_vul_keyword, args.runs)
                sql = str(
                    select(Vul).where(Vul.title.ilike("%SQL注入%")).limit(20).compile(
                        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
                    )
                )
                for line in (await session.execute(
                    text(f"EXPLAIN (ANALYZE, BUFFERS) {sql}")
                )).all():
                    print(f"RESULT   {line[0]}")

    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE'))
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="列表查询性能基准（独立 schema，可重复）")
    parser.add_argument("--vulns", type=int, default=100_000)
    parser.add_argument("--plans", type=int, default=10_000)
    parser.add_argument("--reports", type=int, default=10_000)
    parser.add_argument("--nonpen", type=int, default=5_000)
    parser.add_argument("--logs", type=int, default=20_000)
    parser.add_argument("--runs", type=int, default=7)
    parser.add_argument("--explain", action="store_true", help="输出 EXPLAIN (ANALYZE, BUFFERS)")
    parser.add_argument(
        "--trgm", action="store_true",
        help="评估 pg_trgm：对比前后通配符检索在 GIN 三元组索引前后的延迟与执行计划",
    )
    args = parser.parse_args()
    if not os.environ.get("VP_DATABASE_URL"):
        raise SystemExit("必须显式设置 VP_DATABASE_URL（脚本会自建/删除独立 schema）")
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
