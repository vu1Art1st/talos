"""Excel 响应统一封装：所有 xlsx 导出接口共用，禁止在路由内散落 BytesIO/StreamingResponse 样板。"""
from io import BytesIO
from urllib.parse import quote

from fastapi.responses import StreamingResponse

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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
