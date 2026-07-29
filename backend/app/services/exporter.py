"""PDF 转换：调用 Gotenberg（LibreOffice 引擎），保证与 Word 版式一致。"""
import hashlib
import os
import time
from pathlib import Path

import httpx

from app.core.config import settings

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


async def convert_docx_to_pdf(docx_path: str, pdf_path: str) -> str:
    url = f"{settings.GOTENBERG_URL.rstrip('/')}/forms/libreoffice/convert"
    data = Path(docx_path).read_bytes()
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            url,
            files={"files": (Path(docx_path).name, data, DOCX_MIME)},
        )
        resp.raise_for_status()
    out = Path(pdf_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(resp.content)
    return pdf_path


async def ensure_pdf_preview(src_path: str) -> str:
    """确保存在可预览的 PDF：pdf 原样返回，docx 转换后缓存到 storage/previews。

    缓存 key 含源文件 mtime，源文件更新后自动重新转换；缓存命中时续期 mtime，
    配合 cleanup_stale_previews 实现「关闭 30 分钟内未再打开即清理」。
    """
    src = Path(src_path)
    if not src.exists():
        raise FileNotFoundError(f"源文件不存在: {src_path}")
    if src.suffix.lower() == ".pdf":
        return str(src)
    preview_dir = settings.storage_sub("previews")
    key = hashlib.md5(f"{src.resolve()}|{src.stat().st_mtime_ns}".encode()).hexdigest()
    pdf_path = preview_dir / f"{key}.pdf"
    if pdf_path.exists():
        os.utime(pdf_path)  # 再次打开，续期
        return str(pdf_path)
    return await convert_docx_to_pdf(str(src), str(pdf_path))


def cleanup_stale_previews(ttl_minutes: int = 30) -> int:
    """删除超过 TTL 未被再次打开（mtime 未续期）的预览 PDF，返回删除数量。"""
    preview_dir = settings.storage_sub("previews")
    deadline = time.time() - ttl_minutes * 60
    removed = 0
    for f in preview_dir.glob("*.pdf"):
        try:
            if f.stat().st_mtime < deadline:
                f.unlink()
                removed += 1
        except OSError:  # 文件正被占用等，留待下轮清理
            pass
    return removed
