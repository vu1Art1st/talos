"""远程漏洞 Markdown 转换安全与结构测试。"""
import pytest
from fastapi import HTTPException

from app.services.markdown_service import render_markdown


def test_render_markdown_generates_html_and_tiptap_json():
    rendered = render_markdown(
        "## 漏洞标题\n\n**粗体** 和 *斜体*\n\n"
        "- 第一项\n- 第二项\n\n"
        "|列A|列B|\n|-|-|\n|1|2|",
    )

    assert "<h2>" in rendered.html
    assert "<strong>" in rendered.html
    assert "<table>" in rendered.html
    assert rendered.json["type"] == "doc"
    assert {node["type"] for node in rendered.json["content"]} >= {
        "paragraph", "bulletList", "table",
    }


def test_raw_html_is_escaped_not_executed():
    rendered = render_markdown("<script>alert(1)</script>\n\n正常内容")

    assert "<script>" not in rendered.html
    assert "alert(1)" in rendered.html
    assert "正常内容" in rendered.html


def test_markdown_rejects_remote_and_data_images():
    with pytest.raises(HTTPException) as remote:
        render_markdown("![x](https://example.com/a.png)")
    assert remote.value.status_code == 422

    with pytest.raises(HTTPException) as data:
        render_markdown("![x](data:image/png;base64,AAAA)")
    assert data.value.status_code == 422


def test_markdown_accepts_local_uploaded_image_path():
    name = "a" * 32 + ".png"
    rendered = render_markdown(f"![截图](/storage/uploads/images/{name})")

    assert rendered.image_names == (name,)
    assert rendered.json["content"][0]["content"][0]["type"] == "image"


def test_markdown_rejects_empty_rendered_content():
    with pytest.raises(HTTPException) as exc:
        render_markdown("   \n\n")
    assert exc.value.status_code == 422
