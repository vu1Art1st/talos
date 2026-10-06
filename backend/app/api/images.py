"""图片下发端点：需登录（安全审计 TALOS-2026-006 / 批次 E-1 修复）。

背景：`/storage/uploads/images` 原为 `StaticFiles` 匿名直出，报告截图（常含内网地址、
账号、令牌等敏感信息）在 URL 泄露后（浏览器历史、日志、转发）可被任意人读取。

修复方式：**保持 URL 路径不变**，改为需登录下发。路径不变是有意为之：
- 存量富文本与 docx 导入解析写入的 `img src` 全是该路径；若改前缀，
  报告导出的 `_localize_images`（按 `/storage/` 前缀与文件名本地化）会失效，图片将从导出文档中丢失；
- 前端渲染的是库内 HTML（`v-html`），无法逐张改造 src。

凭证来源（见 `core/deps.get_image_viewer`）：
1. 浏览器：登录/刷新/改密时下发的 `vp_img` Cookie（HttpOnly、`Path=/storage/uploads/images`、
   SameSite=Lax，JS 读不到、不会随其它请求发送）；
2. API 客户端：`Authorization: Bearer <access token 或 tlp_ 个人访问令牌>`。
两者皆无 → 401。
"""
import mimetypes
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.avatars import preset_file
from app.core.data_scope import bound_scope_statement
from app.core.deps import get_image_viewer
from app.core.storage import resolve_storage_path
from app.db import async_session_maker, get_session
from app.models import ImportRecord, KnowledgeEntry, ReportSection, User, Vul

router = APIRouter(tags=["图片"])

# 文件名白名单：与 /upload/image 的产物一致（uuid4 hex + 图片扩展名），
# 顺带彻底排除目录穿越（即便不依赖 resolve_storage_path 的边界校验）
_IMAGE_NAME_RE = re.compile(r"^[0-9a-f]{32}\.(?:png|jpe?g|gif|webp|bmp)$")


# 富文本中可能引用 `/storage/uploads/images/<name>` 的列，是图片鉴权的唯一查询依据。
# 这些列必须与 `scripts/enable_trgm_indexes.py` 的 TRGM_INDEXES 保持一致：图片文件名是
# 32 位十六进制串，`%name%` 前导通配只有 trgm GIN 索引可用，否则每次图片请求都会退化成
# 全表扫描（批次 E-1.1）。漂移守卫见 `tests/test_image_reference_indexes.py`。
IMAGE_REFERENCE_COLUMNS: dict[type, tuple[str, ...]] = {
    ReportSection: ("content_html",),
    Vul: ("description_html", "reproduce_html", "solution_html", "retest_html"),
    ImportRecord: ("description_html", "reproduce_html", "solution_html", "retest_html"),
    KnowledgeEntry: ("description_html", "harm_html", "solution_html"),
}


def _reference_stmt(model, name: str):
    columns = IMAGE_REFERENCE_COLUMNS[model]
    conditions = [getattr(model, column).contains(name) for column in columns]
    return select(model.id).where(or_(*conditions)).limit(1)


async def _has_visible_reference(session: AsyncSession, name: str) -> bool:
    for model in (ReportSection, Vul, ImportRecord, KnowledgeEntry):
        stmt = bound_scope_statement(session, _reference_stmt(model, name))
        if (await session.execute(stmt)).scalar_one_or_none() is not None:
            return True
    return False


async def _has_any_reference(name: str) -> bool:
    async with async_session_maker() as session:
        for model in (ReportSection, Vul, ImportRecord, KnowledgeEntry):
            if (await session.execute(_reference_stmt(model, name))).scalar_one_or_none() is not None:
                return True
    return False


@router.get("/storage/uploads/images/{name}")
async def download_image(
    name: str,
    _: User = Depends(get_image_viewer),
    session: AsyncSession = Depends(get_session),
):
    """下发富文本图片（需登录 + 对象 scope；越界/越权/不存在统一 404）。"""
    if not _IMAGE_NAME_RE.match(name):
        raise HTTPException(404, "图片不存在")
    if not await _has_visible_reference(session, name) and await _has_any_reference(name):
        raise HTTPException(404, "图片不存在")
    path = resolve_storage_path(f"uploads/images/{name}", not_found_detail="图片不存在")
    media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    # private：凭证相关资源不得进共享缓存；max-age 让浏览器复用，避免同页多图重复请求
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/storage/avatars/zzz/{version}/{name}")
async def download_preset_avatar(
    version: str,
    name: str,
    _: User = Depends(get_image_viewer),
):
    """预置头像：随镜像分发的静态资源，经鉴权端点下发（不挂 StaticFiles）。

    两段路径都来自 URL，但不会参与自由拼接：先与 app.constants.AVATAR_PRESETS
    白名单比对，命中后只读取白名单 id 对应的固定文件，未命中一律 404。
    """
    if not name.endswith(".webp"):
        raise HTTPException(404, "头像不存在")
    path = preset_file(f"zzz/{version}/{name[:-5]}")
    if path is None:
        raise HTTPException(404, "头像不存在")
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "private, max-age=86400"},
    )
