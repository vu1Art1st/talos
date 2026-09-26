"""后台任务生命周期与幂等测试（ROADMAP P0-3）。

覆盖验收要求里的四条故障路径：
- **崩溃**：强制中断（超租约）的 running/parsing 任务在下一轮扫描中被回收；
- **重复投递**：同一幂等键的通知只产生一次副作用；
- **永久失败**：文件损坏 / 数据缺失类错误不重试，直接进死信并保留原因；
- **恢复成功**：回收后的任务可被重新执行并正常完成。
"""
import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.timeutil import now
from app.db import async_session_maker
from app.models import ExportJob, Report, TaskDedupKey
from app.services import task_dedup, task_lifecycle

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_retry_classification_and_backoff():
    """可重试 / 永久错误的分类口径与指数退避时长。"""
    assert task_lifecycle.is_retryable(RuntimeError("connection reset"))
    assert task_lifecycle.is_retryable(asyncio.TimeoutError())
    # 永久错误：重试没有意义，直接进死信
    assert not task_lifecycle.is_retryable(task_lifecycle.PermanentTaskError("模板缺失"))
    assert not task_lifecycle.is_retryable(FileNotFoundError("no such file: x.docx"))
    assert not task_lifecycle.is_retryable(ValueError("报告不存在"))

    base = max(settings.TASK_BACKOFF_SECONDS, 1)
    assert task_lifecycle.backoff_seconds(1) == base
    assert task_lifecycle.backoff_seconds(2) == base * 2
    assert task_lifecycle.backoff_seconds(3) == base * 4
    assert task_lifecycle.backoff_seconds(99) == 3600  # 封顶


async def test_lease_and_dead_letter_state_machine():
    """租约 → 心跳续租 → 可重试回排队 / 永久失败进死信（纯状态机，不依赖数据库）。"""
    job = ExportJob(report_id=1, status="pending")
    task_lifecycle.start_lease(job)
    assert job.attempts == 1 and job.lease_until and job.last_heartbeat

    first_lease = job.lease_until
    task_lifecycle.heartbeat(job)
    assert job.lease_until >= first_lease

    assert task_lifecycle.plan_retry(job, RuntimeError("boom")) is True
    assert job.status == "pending" and job.next_retry_at is not None

    # 超过最大尝试次数 → 死信，不再安排重试（即使错误本身可重试）
    job.attempts = settings.TASK_MAX_ATTEMPTS
    assert task_lifecycle.plan_retry(job, RuntimeError("boom")) is False
    assert job.status == "failed" and job.dead_letter_reason and job.next_retry_at is None

    # 永久错误一次即死信
    fresh = ExportJob(report_id=1, status="pending")
    task_lifecycle.start_lease(fresh)
    assert task_lifecycle.plan_retry(fresh, ValueError("报告不存在")) is False
    assert fresh.status == "failed" and fresh.next_retry_at is None


async def test_crash_recovery_requeues_expired_lease_and_dead_letters_exhausted(client):
    """崩溃恢复：超租约任务回排队等待重试；已达最大次数的任务明确失败并保留原因。"""
    async with async_session_maker() as session:
        report = Report(title="任务回收测试报告")
        session.add(report)
        await session.flush()
        stale = ExportJob(
            report_id=report.id, status="running", attempts=1,
            lease_until=now() - timedelta(seconds=5),
            last_heartbeat=now() - timedelta(seconds=60),
        )
        exhausted = ExportJob(
            report_id=report.id, status="running", attempts=settings.TASK_MAX_ATTEMPTS,
            lease_until=now() - timedelta(seconds=5),
        )
        healthy = ExportJob(
            report_id=report.id, status="running", attempts=1,
            lease_until=now() + timedelta(seconds=600), last_heartbeat=now(),
        )
        session.add_all([stale, exhausted, healthy])
        await session.commit()
        report_id, stale_id, exhausted_id, healthy_id = (
            report.id, stale.id, exhausted.id, healthy.id,
        )

    summary = await task_lifecycle.recover_stale_tasks()
    assert summary["requeued"] >= 1 and summary["dead"] >= 1

    async with async_session_maker() as session:
        stale_row = await session.get(ExportJob, stale_id)
        exhausted_row = await session.get(ExportJob, exhausted_id)
        healthy_row = await session.get(ExportJob, healthy_id)
        assert stale_row.status == "pending" and stale_row.next_retry_at is not None
        assert stale_row.lease_until is None
        assert exhausted_row.status == "failed" and exhausted_row.dead_letter_reason
        assert healthy_row.status == "running"  # 租约未过期：不得误回收
        for row in (stale_row, exhausted_row, healthy_row):
            await session.delete(row)
        await session.flush()
        await session.delete(await session.get(Report, report_id))
        await session.commit()


async def test_recovered_task_can_run_to_completion(client):
    """恢复成功：回收为可重试后的导出任务重新执行，正常完成并落 file_path。"""
    from app.workers.main import export_report_task

    async with async_session_maker() as session:
        report = Report(title="恢复成功测试报告")
        session.add(report)
        await session.flush()
        job = ExportJob(
            report_id=report.id, status="running", attempts=1,
            lease_until=now() - timedelta(seconds=5),
        )
        session.add(job)
        await session.commit()
        report_id, job_id = report.id, job.id

    await task_lifecycle.recover_stale_tasks()
    async with async_session_maker() as session:
        assert (await session.get(ExportJob, job_id)).status == "pending"

    await export_report_task({}, job_id)
    async with async_session_maker() as session:
        row = await session.get(ExportJob, job_id)
        report = await session.get(Report, report_id)
        assert row.status == "done", row.error
        assert row.file_path and row.lease_until is None
        assert row.finish_time is not None
        assert report.version >= 2  # 初始 1 + 本次导出 +1
        await session.delete(row)
        await session.flush()
        await session.delete(report)
        await session.commit()


async def test_completed_export_is_not_regenerated_on_retry(client):
    """重复投递：已完成的导出任务再次执行直接短路，不重复提升导出版本号。"""
    from app.workers.main import export_report_task

    async with async_session_maker() as session:
        report = Report(title="导出幂等测试报告")
        session.add(report)
        await session.flush()
        job = ExportJob(report_id=report.id, status="done", file_path="already.docx")
        session.add(job)
        await session.commit()
        report_id, job_id, version = report.id, job.id, report.version

    await export_report_task({}, job_id)
    async with async_session_maker() as session:
        row = await session.get(ExportJob, job_id)
        assert (await session.get(Report, report_id)).version == version
        assert row.status == "done" and row.attempts == 0  # 未进入执行体
        await session.delete(row)
        await session.flush()
        await session.delete(await session.get(Report, report_id))
        await session.commit()


async def _make_delivery(session):
    """建一条待投递记录（+ 关联渠道），返回 (delivery_id, channel_id)。"""
    from app.models import NotificationChannel, NotifyDelivery

    channel = NotificationChannel(
        name=f"测试渠道-{uuid4().hex[:6]}", type="email",
        config={"recipients": ["a@b.c"]}, events=[],
    )
    session.add(channel)
    await session.flush()
    row = NotifyDelivery(
        channel_id=channel.id, channel_name=channel.name, channel_type=channel.type,
        event="vuln_created", title="标题", content="正文", status="pending",
    )
    session.add(row)
    await session.commit()
    return row.id, channel.id


async def _drop_delivery(delivery_id: int, channel_id: int) -> None:
    from app.models import NotificationChannel, NotifyDelivery

    async with async_session_maker() as session:
        row = await session.get(NotifyDelivery, delivery_id)
        if row is not None:
            await session.delete(row)
        channel = await session.get(NotificationChannel, channel_id)
        if channel is not None:
            await session.delete(channel)
        await session.commit()


async def test_notify_delivery_success_is_not_resent(client, monkeypatch):
    """投递记录是幂等锚点（P1-3）：成功后重投直接短路，不产生第二次外呼。"""
    calls: list[str] = []

    async def fake_send(channel_type, config, title, body):
        calls.append(title)
        return 200, ""

    monkeypatch.setattr("app.services.notify_service.perform_send", fake_send)
    from app.models import NotifyDelivery
    from app.workers.main import send_notify_task

    async with async_session_maker() as session:
        delivery_id, channel_id = await _make_delivery(session)

    await send_notify_task({}, delivery_id)
    await send_notify_task({}, delivery_id)  # 已成功 → 短路
    assert calls == ["标题"]

    async with async_session_maker() as session:
        row = await session.get(NotifyDelivery, delivery_id)
        assert row.status == "success" and row.attempts == 1 and row.finish_time is not None
    await _drop_delivery(delivery_id, channel_id)


async def test_notify_delivery_retry_then_dead_letter(client, monkeypatch):
    """可重试错误 → failed + next_retry_at；永久错误 → dead 且保留原因（P1-3）。"""
    retryable = {"flag": True}

    async def fake_send(channel_type, config, title, body):
        if retryable["flag"]:
            return 0, "[可重试] 网络连接失败：timeout"
        return 400, "对端返回 400（请检查渠道配置：地址、鉴权或收件人）"

    monkeypatch.setattr("app.services.notify_service.perform_send", fake_send)
    from app.models import NotifyDelivery
    from app.workers.main import send_notify_task

    async with async_session_maker() as session:
        delivery_id, channel_id = await _make_delivery(session)

    await send_notify_task({}, delivery_id)
    async with async_session_maker() as session:
        row = await session.get(NotifyDelivery, delivery_id)
        assert row.status == "failed" and row.next_retry_at is not None
        assert "[可重试]" not in row.last_error

    retryable["flag"] = False
    await send_notify_task({}, delivery_id)
    async with async_session_maker() as session:
        row = await session.get(NotifyDelivery, delivery_id)
        assert row.status == "dead" and "400" in row.dead_letter_reason
    await _drop_delivery(delivery_id, channel_id)


async def test_retry_due_deliveries_redelivers(client, monkeypatch):
    """到期待重试记录可被兜底扫描重投（进程重启后不丢失）。"""
    from datetime import timedelta

    from app.core.timeutil import now
    from app.models import NotifyDelivery

    async def ok_send(channel_type, config, title, body):
        return 200, ""

    monkeypatch.setattr("app.services.notify_service.perform_send", ok_send)
    from app.services import notify_service

    async with async_session_maker() as session:
        delivery_id, channel_id = await _make_delivery(session)
        row = await session.get(NotifyDelivery, delivery_id)
        row.status = "failed"
        row.next_retry_at = now() - timedelta(seconds=1)
        await session.commit()

    async with async_session_maker() as session:
        assert await notify_service.retry_due_deliveries(session) == 1
        await session.commit()
        assert (await session.get(NotifyDelivery, delivery_id)).status == "success"
    await _drop_delivery(delivery_id, channel_id)


async def test_dedup_key_claim_and_cleanup(client):
    """幂等键抢占语义与过期回收（避免无界增长）。"""
    async with async_session_maker() as session:
        key = f"claim-{uuid4().hex}"
        assert await task_dedup.claim_dedup_key(session, key) is True
        assert await task_dedup.claim_dedup_key(session, key) is False
        await task_dedup.release_dedup_key(session, key)
        assert await task_dedup.claim_dedup_key(session, key) is True

        stale_key = f"stale-{uuid4().hex}"
        session.add(TaskDedupKey(key=stale_key, create_time=now() - timedelta(days=30)))
        await session.commit()
        removed = await task_dedup.cleanup_dedup_keys(session)
        await session.commit()
        assert removed >= 1
        remaining = (
            await session.execute(select(TaskDedupKey).where(TaskDedupKey.key == stale_key))
        ).first()
        assert remaining is None
        for row in (await session.execute(
            select(TaskDedupKey).where(TaskDedupKey.key.in_([key, stale_key]))
        )).scalars().all():
            await session.delete(row)
        await session.commit()
