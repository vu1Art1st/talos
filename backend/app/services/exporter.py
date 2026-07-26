"""PDF 转换：调用 Gotenberg（LibreOffice 引擎），保证与 Word 版式一致。"""
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
