"""压缩包（docx / xlsx 等 OOXML）解压配额校验：zip 炸弹防护（安全审计 批次 E-5）。

背景：docx/xlsx 都是 ZIP 包，解析（python-docx / openpyxl）会把条目解压进内存。
此前对上传文件只校验了**压缩后**大小（如 20MB/50MB），一个 1MB 的高压缩比包可解压出数十 GB，
造成内存/CPU 耗尽（进程级 DoS，比单个请求更严重：arq worker 与 API 同容器资源）。

判定依据取自 ZIP 中央目录（`infolist()` 的 `file_size` / `compress_size`），**不解压**即可判定：
- 条目数超限（大量小条目拖慢解析）；
- 声明解压总量超限（真正的炸弹形态）；
- 压缩比超限（正常文档含图片时压缩比接近 1，纯文本重复内容才会极高）。

阈值经业务形态校准（见 core/config.py 的 ARCHIVE_* 与调用处的 overrides）：宁松勿误伤——
正常报告含数百张截图时条目数约千级、压缩比接近 1。
"""
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from fastapi import HTTPException

from app.core.config import settings

_QUOTA_MSG = "文档结构异常（解压后体积或条目数超出限制），已拒绝处理"


def assert_archive_quota(
    source: str | Path | bytes,
    *,
    max_entries: int | None = None,
    max_uncompressed_mb: int | None = None,
    max_ratio: int | None = None,
) -> None:
    """解压前配额校验；超限抛 400。非 ZIP（坏包）直接放行，交由调用方原有的解析错误处理。

    source 可为路径或字节流（xlsx 走字节流，docx 走落盘路径）。
    """
    max_entries = settings.ARCHIVE_MAX_ENTRIES if max_entries is None else max_entries
    max_uncompressed_mb = (
        settings.ARCHIVE_MAX_UNCOMPRESSED_MB if max_uncompressed_mb is None else max_uncompressed_mb
    )
    max_ratio = settings.ARCHIVE_MAX_RATIO if max_ratio is None else max_ratio
    try:
        with ZipFile(BytesIO(source) if isinstance(source, bytes) else Path(source)) as zf:
            infos = zf.infolist()
            total_uncompressed = sum(i.file_size for i in infos)
            total_compressed = sum(i.compress_size for i in infos)
    except (BadZipFile, OSError):
        # 不是合法 ZIP：由调用方的解析流程给出「文件不可解析」的既有文案
        return
    ratio = total_uncompressed / total_compressed if total_compressed else float(total_uncompressed)
    if (
        len(infos) > max_entries
        or total_uncompressed > max_uncompressed_mb * 1024 * 1024
        or ratio > max_ratio
    ):
        raise HTTPException(400, _QUOTA_MSG)
