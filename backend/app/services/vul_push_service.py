"""开放 API：远程 Agent 漏洞推送与图片上传。"""
import hashlib
import mimetypes
import uuid
from datetime import timedelta
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.images import ALLOWED_IMAGE_EXT, is_allowed_image
from app.core.storage import resolve_storage_path
from app.core.timeutil import now
from app.models import (
    Asset,
    TestingPlan,
    User,
    Vul,
    VulExternalImage,
    VulExternalRef,
    VulnType,
)
from app.schemas import VulImageUploadOut, VulPushIn, VulPushItemResultOut, VulPushOut, VulPushSummaryOut
from app.services import plan_service, sla_service, stats_cache, vul_service
from app.services.idempotency import payload_hash
from app.services.markdown_service import CONVERTER_VERSION, render_markdown

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_SIDE = 8192
IMAGE_URL_PREFIX = "/storage/uploads/images/"


async def _load_plan_for_push(
    session: AsyncSession, plan_id: int, user: User,
) -> TestingPlan:
    plan = await plan_service.get_plan_for_update(session, plan_id)
    if plan is None:
        raise HTTPException(404, "渗透测试工单不存在")
    if not plan_service.is_plan_claimant(user, plan):
        raise HTTPException(403, "仅已认领该渗透测试工单的账号可推送漏洞或上传图片")
    return plan


def _normalize_source_system(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise HTTPException(422, "来源系统不能为空")
    if len(value) > 64:
        raise HTTPException(422, "来源系统不能超过 64 个字符")
    return value


def _normalize_external_image_id(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > 191:
        raise HTTPException(422, "external_image_id 不能超过 191 个字符")
    return value


def _validate_image_payload(filename: str, data: bytes) -> tuple[str, str]:
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise HTTPException(400, f"不支持的图片格式: {ext or '无扩展名'}")
    if not data:
        raise HTTPException(400, "图片内容为空")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(400, "图片大小不能超过 10MB")
    if not is_allowed_image(data):
        raise HTTPException(400, "文件内容不是有效的图片")
    try:
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
            if width > MAX_IMAGE_SIDE or height > MAX_IMAGE_SIDE:
                raise HTTPException(400, "图片尺寸不能超过 8192x8192")
            actual = (image.format or "").upper()
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise HTTPException(400, "文件内容不是有效的图片") from exc
    expected_ext = {
        "PNG": {".png"},
        "JPEG": {".jpg", ".jpeg"},
        "GIF": {".gif"},
        "WEBP": {".webp"},
    }.get(actual, set())
    if ext not in expected_ext:
        raise HTTPException(400, "图片扩展名与实际格式不一致")
    mime_type = mimetypes.guess_type(f"image{ext}")[0] or "application/octet-stream"
    return ext, mime_type


def _image_out(record: VulExternalImage, *, result: str) -> VulImageUploadOut:
    url = f"{IMAGE_URL_PREFIX}{record.file_name}"
    return VulImageUploadOut(
        image_id=record.external_image_id or record.sha256,
        url=url,
        markdown=f"![漏洞截图]({url})",
        sha256=record.sha256,
        size_bytes=record.size_bytes,
        content_type=record.mime_type,
        result=result,
    )


async def _find_external_image(
    session: AsyncSession,
    *,
    plan_id: int,
    source_system: str,
    external_image_id: str | None,
    sha256: str,
) -> VulExternalImage | None:
    if external_image_id:
        existing = (
            await session.execute(
                select(VulExternalImage).where(
                    VulExternalImage.plan_id == plan_id,
                    VulExternalImage.source_system == source_system,
                    VulExternalImage.external_image_id == external_image_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.sha256 != sha256:
                raise HTTPException(409, "同一 external_image_id 已上传不同内容")
            return existing
    return (
        await session.execute(
            select(VulExternalImage).where(
                VulExternalImage.plan_id == plan_id,
                VulExternalImage.source_system == source_system,
                VulExternalImage.sha256 == sha256,
            )
        )
    ).scalar_one_or_none()


async def upload_external_image(
    session: AsyncSession,
    *,
    plan_id: int,
    user: User,
    source_system: str,
    external_image_id: str | None,
    filename: str,
    data: bytes,
) -> VulImageUploadOut:
    """保存 Agent 图片并返回可直接嵌入 Markdown 的片段。"""
    source_system = _normalize_source_system(source_system)
    external_image_id = _normalize_external_image_id(external_image_id)
    await _load_plan_for_push(session, plan_id, user)

    sha256 = hashlib.sha256(data).hexdigest()
    existing = await _find_external_image(
        session,
        plan_id=plan_id,
        source_system=source_system,
        external_image_id=external_image_id,
        sha256=sha256,
    )
    if existing is not None:
        return _image_out(existing, result="duplicated")

    ext, mime_type = _validate_image_payload(filename, data)
    file_name = f"{uuid.uuid4().hex}{ext}"
    image_dir = settings.storage_sub("uploads", "images")
    image_dir.mkdir(parents=True, exist_ok=True)
    path = image_dir / file_name
    path.write_bytes(data)

    record = VulExternalImage(
        plan_id=plan_id,
        source_system=source_system,
        external_image_id=external_image_id,
        file_name=file_name,
        mime_type=mime_type,
        size_bytes=len(data),
        sha256=sha256,
        uploader_id=user.id,
    )
    try:
        async with session.begin_nested():
            session.add(record)
            await session.flush()
    except IntegrityError:
        path.unlink(missing_ok=True)
        existing = await _find_external_image(
            session,
            plan_id=plan_id,
            source_system=source_system,
            external_image_id=external_image_id,
            sha256=sha256,
        )
        if existing is None:
            raise
        return _image_out(existing, result="duplicated")

    await session.commit()
    return _image_out(record, result="created")


def _advisory_lock_key(source_system: str, external_id: str) -> int:
    digest = hashlib.blake2b(
        f"{source_system}\x00{external_id}".encode("utf-8"), digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big", signed=True)


def _item_hash(source_system: str, plan_id: int, item) -> str:
    payload = item.model_dump(mode="json")
    payload["asset_ids"] = sorted(payload["asset_ids"])
    payload["source_system"] = source_system
    payload["testing_plan_id"] = plan_id
    return payload_hash(payload)


async def push_vulnerabilities(
    session: AsyncSession,
    *,
    plan_id: int,
    user: User,
    body: VulPushIn,
) -> VulPushOut:
    """在指定工单批量创建漏洞；整批原子提交。"""
    plan = await _load_plan_for_push(session, plan_id, user)
    type_codes = {item.vul_type for item in body.items}
    known_types = set(
        (
            await session.execute(
                select(VulnType.code).where(VulnType.code.in_(type_codes))
            )
        ).scalars()
    )
    missing_types = sorted(type_codes - known_types)
    if missing_types:
        raise HTTPException(422, f"无效的漏洞类型: {missing_types}")

    asset_ids = {asset_id for item in body.items for asset_id in item.asset_ids}
    assets = (
        await session.execute(select(Asset).where(Asset.id.in_(asset_ids)))
    ).scalars().all() if asset_ids else []
    asset_map = {asset.id: asset for asset in assets}
    if set(asset_map) != asset_ids:
        raise HTTPException(400, "存在无效的资产ID")

    rendered = [
        (
            item,
            render_markdown(item.description_md, field_name=f"{item.external_id}.description_md"),
            render_markdown(item.reproduce_md, field_name=f"{item.external_id}.reproduce_md"),
            render_markdown(item.solution_md, field_name=f"{item.external_id}.solution_md"),
        )
        for item in body.items
    ]
    image_names = {
        name
        for _item, description, reproduce, solution in rendered
        for name in (*description.image_names, *reproduce.image_names, *solution.image_names)
    }
    image_rows = (
        await session.execute(
            select(VulExternalImage).where(
                VulExternalImage.plan_id == plan.id,
                VulExternalImage.source_system == body.source_system,
                VulExternalImage.file_name.in_(image_names),
            )
        )
    ).scalars().all() if image_names else []
    found_images = {row.file_name for row in image_rows}
    missing_images = sorted(image_names - found_images)
    if missing_images:
        raise HTTPException(422, f"Markdown 引用了未上传的图片: {missing_images}")

    for item in sorted(body.items, key=lambda row: (body.source_system, row.external_id)):
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": _advisory_lock_key(body.source_system, item.external_id)},
        )

    refs = (
        await session.execute(
            select(VulExternalRef).where(
                VulExternalRef.source_system == body.source_system,
                VulExternalRef.external_id.in_([item.external_id for item in body.items]),
            )
        )
    ).scalars().all()
    ref_map = {ref.external_id: ref for ref in refs}

    sla_config = await sla_service.get_config(session)
    sla_policies = await sla_service.load_policies(session)
    results: list[VulPushItemResultOut] = []
    created = 0
    duplicated = 0
    for item, description, reproduce, solution in rendered:
        digest = _item_hash(body.source_system, plan.id, item)
        existing = ref_map.get(item.external_id)
        if existing is not None:
            if existing.testing_plan_id != plan.id or existing.payload_hash != digest:
                raise HTTPException(
                    409,
                    f"external_id「{item.external_id}」已存在且内容不同，"
                    "v1 不支持覆盖已有漏洞",
                )
            existing.last_push_time = now()
            existing.last_operator_id = user.id
            results.append(VulPushItemResultOut(
                external_id=item.external_id, vul_id=existing.vul_id, result="duplicated",
            ))
            duplicated += 1
            continue

        vul = Vul(
            title=item.title,
            vul_type=item.vul_type,
            level=item.level,
            source=0,
            layer=item.layer,
            affected_url=item.affected_url,
            description_html=description.html,
            description_json=description.json,
            reproduce_html=reproduce.html,
            reproduce_json=reproduce.json,
            solution_html=solution.html,
            solution_json=solution.json,
            score=item.score,
            risk_score=item.risk_score,
            left_risk_score=item.left_risk_score,
            asset_level=item.asset_level,
            cvss_vector=item.cvss_vector,
            testing_plan_id=plan.id,
            submitter_id=user.id,
        )
        vul.assets = [asset_map[asset_id] for asset_id in item.asset_ids]
        session.add(vul)
        await session.flush()
        sla_service.apply_to_vul(vul, sla_config, sla_policies)
        vul_service.add_log(session, vul, user, "创建漏洞", "开放API远程推送")
        session.add(VulExternalRef(
            vul_id=vul.id,
            testing_plan_id=plan.id,
            source_system=body.source_system,
            external_id=item.external_id,
            payload_hash=digest,
            source_payload_json={
                "description_md": item.description_md,
                "reproduce_md": item.reproduce_md,
                "solution_md": item.solution_md,
            },
            converter_version=CONVERTER_VERSION,
            last_operator_id=user.id,
        ))
        results.append(VulPushItemResultOut(
            external_id=item.external_id, vul_id=vul.id, result="created",
        ))
        created += 1

    used_at = now()
    for image in image_rows:
        image.last_used_time = used_at
    if created:
        await plan_service.reopen_passed_plan(session, plan.id)
        await vul_service.sync_plan_retest_state(session, plan_ids=[plan.id])
        await plan_service.refresh_stats(session, plan.id)

    await session.commit()
    if created:
        stats_cache.invalidate()
    return VulPushOut(
        plan_id=plan.id,
        summary=VulPushSummaryOut(created=created, duplicated=duplicated),
        items=results,
    )


async def cleanup_orphan_images(session: AsyncSession, *, hours: int = 24) -> int:
    """清理超过保留期且从未被漏洞正文使用的 Agent 图片。"""
    cutoff = now() - timedelta(hours=hours)
    rows = (
        await session.execute(
            select(VulExternalImage).where(
                VulExternalImage.last_used_time.is_(None),
                VulExternalImage.create_time < cutoff,
            )
        )
    ).scalars().all()
    removed = 0
    for row in rows:
        referenced = await session.scalar(
            select(Vul.id).where(
                (Vul.description_html.contains(row.file_name))
                | (Vul.reproduce_html.contains(row.file_name))
                | (Vul.solution_html.contains(row.file_name))
            ).limit(1)
        )
        if referenced is not None:
            continue
        try:
            resolve_storage_path(
                f"uploads/images/{row.file_name}", not_found_detail="图片不存在",
            ).unlink(missing_ok=True)
        except HTTPException:
            pass
        await session.delete(row)
        removed += 1
    return removed
