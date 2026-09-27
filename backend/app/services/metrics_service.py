"""P2-5 运行指标：输出 Prometheus 文本格式，不包含对象名、URL、令牌或错误正文。"""
import json
import shutil
import time
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import event, func, select, text

from app.core.config import settings
from app.db import async_session_maker, engine
from app.models import ExportJob, ImportBatch, NotifyDelivery
from app.services.health_service import probe_dependencies

_db_queries = 0
_db_slow_queries = 0
_db_query_seconds = 0.0
_SLOW_QUERY_SECONDS = 0.5


@event.listens_for(engine.sync_engine, "before_cursor_execute")
def _before_cursor_execute(_conn, _cursor, _statement, _parameters, context, _executemany):
    context._talos_started_at = time.perf_counter()


@event.listens_for(engine.sync_engine, "after_cursor_execute")
def _after_cursor_execute(_conn, _cursor, _statement, _parameters, context, _executemany):
    global _db_queries, _db_slow_queries, _db_query_seconds
    started = getattr(context, "_talos_started_at", None)
    if started is None:
        return
    elapsed = max(time.perf_counter() - started, 0.0)
    _db_queries += 1
    _db_query_seconds += elapsed
    if elapsed >= _SLOW_QUERY_SECONDS:
        _db_slow_queries += 1


def _line(name: str, value: int | float, **labels: str) -> str:
    if labels:
        rendered = ",".join(
            f'{key}="{str(val).replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'
            for key, val in sorted(labels.items())
        )
        return f"{name}{{{rendered}}} {value}"
    return f"{name} {value}"


async def _task_counts(session) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    specs = (
        ("export", ExportJob, ("pending", "running", "done", "failed")),
        ("import", ImportBatch, ("pending", "parsing", "parsed", "confirmed", "failed")),
        ("notify", NotifyDelivery, ("pending", "success", "failed", "dead")),
    )
    for name, model, statuses in specs:
        counts = {}
        for status in statuses:
            counts[status] = int(
                (await session.execute(
                    select(func.count(model.id)).where(model.status == status)
                )).scalar_one()
            )
        out[name] = counts
    return out


def _backup_metrics() -> list[str]:
    root = Path(settings.BACKUP_DIR)
    latest = root / "latest"
    drill = root / "restore_drills" / "latest.json"
    lines = [_line("talos_backup_present", int(latest.exists()))]
    if latest.exists():
        try:
            ts = latest.resolve().stat().st_mtime
            lines.append(_line("talos_backup_age_seconds", max(time.time() - ts, 0.0)))
        except OSError:
            lines.append(_line("talos_backup_age_seconds", -1))
    else:
        lines.append(_line("talos_backup_age_seconds", -1))

    lines.append(_line("talos_restore_drill_report_present", int(drill.exists())))
    if drill.exists():
        try:
            payload = json.loads(drill.read_text(encoding="utf-8"))
            lines.append(_line("talos_restore_drill_success", int(bool(payload.get("success")))))
            finished_at = float(payload.get("finished_at_epoch") or 0)
            lines.append(_line(
                "talos_restore_drill_age_seconds",
                max(time.time() - finished_at, 0.0) if finished_at else -1,
            ))
        except (OSError, ValueError, TypeError):
            lines.append(_line("talos_restore_drill_success", 0))
            lines.append(_line("talos_restore_drill_age_seconds", -1))
    else:
        lines.append(_line("talos_restore_drill_success", 0))
        lines.append(_line("talos_restore_drill_age_seconds", -1))
    return lines


def _disk_metrics() -> list[str]:
    try:
        usage = shutil.disk_usage(settings.storage_path)
        ratio = usage.used / usage.total if usage.total else 0.0
        return [
            _line("talos_disk_total_bytes", usage.total),
            _line("talos_disk_used_bytes", usage.used),
            _line("talos_disk_used_ratio", ratio),
        ]
    except OSError:
        return [_line("talos_disk_used_ratio", -1)]


def _pool_metrics() -> list[str]:
    pool = engine.pool
    lines = []
    for metric in ("size", "checkedin", "checkedout", "overflow"):
        fn = getattr(pool, metric, None)
        if callable(fn):
            try:
                lines.append(_line(f"talos_db_pool_{metric}", fn()))
            except Exception:  # noqa: BLE001  指标采集不得影响主请求
                lines.append(_line(f"talos_db_pool_{metric}", -1))
    return lines


async def collect_metrics(app: FastAPI) -> str:
    """采集当前实例指标；单项失败降级为 -1 / 0，不影响其它指标。"""
    checks, _ready = await probe_dependencies(app)
    lines = [_line("talos_app_up", 1)]
    lines.extend(_pool_metrics())
    lines.extend(_disk_metrics())
    lines.extend(_backup_metrics())
    lines.extend([
        _line("talos_db_queries_total", _db_queries),
        _line("talos_db_slow_queries_total", _db_slow_queries),
        _line("talos_db_query_seconds_total", round(_db_query_seconds, 6)),
    ])
    for name, check in checks.items():
        lines.append(_line("talos_dependency_up", int(bool(check.get("ok"))), dependency=name))
        lines.append(_line(
            "talos_dependency_required", int(bool(check.get("required"))), dependency=name,
        ))

    async with async_session_maker() as session:
        try:
            size = int((await session.execute(
                text("SELECT pg_database_size(current_database())")
            )).scalar_one())
            lines.append(_line("talos_database_size_bytes", size))
        except Exception:  # noqa: BLE001
            lines.append(_line("talos_database_size_bytes", -1))
        try:
            counts = await _task_counts(session)
            for kind, statuses in counts.items():
                for status, value in statuses.items():
                    lines.append(_line("talos_task_count", value, kind=kind, status=status))
        except Exception:  # noqa: BLE001
            lines.append(_line("talos_task_metrics_ok", 0))
    return "\n".join(lines) + "\n"
