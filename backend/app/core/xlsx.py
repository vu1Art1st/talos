"""Excel 读写统一封装：导出响应与上传解析共用，禁止在路由内散落 BytesIO/StreamingResponse 样板。"""
import logging
from io import BytesIO
from urllib.parse import quote
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from app.core.archive import assert_archive_quota

logger = logging.getLogger(__name__)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# 「文件本身不可解析」的可预期异常集合（坏 ZIP / 非 xlsx / 内部 XML 损坏）；
# 其余异常视为服务端缺陷，交由全局兜底处理，避免把自身缺陷伪装成「用户文件有问题」而丢失堆栈（审计 C-3）。
EXCEL_PARSE_ERRORS = (BadZipFile, InvalidFileException, ParseError, KeyError, ValueError)


def xlsx_response(wb, filename: str) -> StreamingResponse:
    """openpyxl Workbook 序列化为附件下载响应（UTF-8 文件名经 RFC 5987 编码）。"""
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


def load_xlsx(data: bytes):
    """解析上传的 .xlsx 字节流（只读、取计算值）。

    解析前先做 ZIP 解压配额校验（安全审计 批次 E-5：xlsx 是高压缩比 ZIP，仅校验压缩后大小
    不足以挡住解压炸弹）；解析失败统一抛 `HTTPException(400)` 并记录原始异常，供导入类复用。
    """
    # 表格类文件条目少、体积可控：比 docx 更严（见 core/archive.py 的阈值口径）
    assert_archive_quota(data, max_entries=500, max_uncompressed_mb=100)
    try:
        return load_workbook(BytesIO(data), read_only=True, data_only=True)
    except EXCEL_PARSE_ERRORS as exc:
        logger.warning("Excel 解析失败（按文件不可解析处理）: %s", exc)
        raise HTTPException(400, "Excel 文件解析失败，请使用导入模板") from exc
