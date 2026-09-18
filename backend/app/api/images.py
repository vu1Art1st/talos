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

from app.core.deps import get_image_viewer
from app.core.storage import resolve_storage_path
from app.models import User

router = APIRouter(tags=["图片"])

# 文件名白名单：与 /upload/image 的产物一致（uuid4 hex + 图片扩展名），
# 顺带彻底排除目录穿越（即便不依赖 resolve_storage_path 的边界校验）
_IMAGE_NAME_RE = re.compile(r"^[0-9a-f]{32}\.(?:png|jpe?g|gif|webp|bmp)$")


@router.get("/storage/uploads/images/{name}")
async def download_image(name: str, _: User = Depends(get_image_viewer)):
    """下发富文本图片（需登录；越界/不存在一律 404）。"""
    if not _IMAGE_NAME_RE.match(name):
        raise HTTPException(404, "图片不存在")
    path = resolve_storage_path(f"uploads/images/{name}", not_found_detail="图片不存在")
    media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    # private：凭证相关资源不得进共享缓存；max-age 让浏览器复用，避免同页多图重复请求
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})
