"""上传文件落盘：统一「扩展名/空文件/大小/魔术字节校验 → UUID 命名 → 写入 storage 子目录」样板。

背景（2026-09-17 审计 B-8）：原结论「远程检测与春耕行动的上传解析流程重复」经复核
**不成立** —— 两者业务差异明确（前者是任意格式附件、后者是 docx 解析出漏洞草稿），
真正的重复只是「读取 → 校验 → UUID 命名 → 落盘 → 返回元信息」这段约 8 行样板，
故只抽取该样板，不强行合并解析逻辑。
"""
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.core.config import settings


async def save_upload(
    file: UploadFile,
    subdir: str,
    *,
    max_bytes: int,
    require_ext: str = "",
    magic: bytes = b"",
    magic_error: str = "文件格式不正确",
    size_error: str = "",
) -> tuple[str, str, int]:
    """校验并落盘上传文件，返回 `(原始文件名, storage 相对路径, 字节数)`。

    - `require_ext`：限定扩展名（如 `.docx`），不匹配即 400；
    - `magic`：文件头字节校验（如 `b"PK\\x03\\x04"`），不匹配即 400（在写入前校验，避免落垃圾文件）；
    - 相对路径统一用 `/` 分隔，便于跨平台写入 DB 与前端展示。
    """
    if require_ext and not (file.filename or "").lower().endswith(require_ext):
        raise HTTPException(400, f"仅支持 {require_ext} 格式的文件")
    data = await file.read()
    if not data:
        raise HTTPException(400, "文件内容为空")
    if len(data) > max_bytes:
        raise HTTPException(400, size_error or f"文件大小不能超过 {max_bytes // (1024 * 1024)}MB")
    if magic and not data.startswith(magic):
        raise HTTPException(400, magic_error)

    ext = Path(file.filename or "").suffix.lower() or require_ext or ".bin"
    name = f"{uuid.uuid4().hex}{ext}"
    rel_path = (Path("uploads") / subdir / name).as_posix()
    dest_dir = settings.storage_sub("uploads", subdir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    (settings.storage_path / rel_path).write_bytes(data)
    return file.filename or name, rel_path, len(data)
