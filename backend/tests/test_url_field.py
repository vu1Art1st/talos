"""影响URL 字段规范化与上限校验（`app/schemas/common.py`）。

背景：该字段曾为 varchar(512)，前端把多条 URL 以换行拼成单字段提交，录入约 20 条即
超出列长，PostgreSQL 抛 StringDataRightTruncation 导致 500；列改为 Text 后长度约束
下沉到 schema 层，本文件固化其唯一口径（切分/去重/条数与单条长度上限）。
"""
import pytest
from pydantic import ValidationError

from app.schemas import ImportRecordUpdateIn, VulIn, VulOut
from app.schemas.common import (
    URL_ITEM_MAX_LENGTH,
    URL_LIST_MAX_COUNT,
    normalize_affected_url,
)
from app.schemas.special import RemoteTestingVulDraft, SpringActionVulDraft

_URL = "https://demo.example.com/api/v1/{n}"


def _urls(count: int) -> list[str]:
    return [_URL.format(n=i) for i in range(count)]


def test_split_by_newline_and_semicolon():
    """换行、CRLF、中英文分号均为分隔符，混合出现同样切分。"""
    raw = "https://a.com/1\nhttps://a.com/2\r\nhttps://a.com/3;https://a.com/4；https://a.com/5"
    assert normalize_affected_url(raw).split("\n") == [f"https://a.com/{i}" for i in range(1, 6)]


def test_trim_drop_empty_and_dedupe_keep_order():
    """逐条 trim、丢弃空项、按首次出现顺序去重。"""
    raw = " https://b.com/2 \n\n  \nhttps://a.com/1\nhttps://b.com/2\n;；https://c.com/3"
    assert normalize_affected_url(raw) == "https://b.com/2\nhttps://a.com/1\nhttps://c.com/3"


def test_blank_input_normalizes_to_empty_string():
    """空值、全空白、纯分隔符统一归一为空串（而非留空行）。"""
    for raw in ("", "   ", "\n\n", ";;；", None):
        assert normalize_affected_url(raw) == ""


def test_upper_bounds_pass():
    """100 条与单条 2048 字符为合法上界，且总长远超旧 varchar(512)。"""
    normalized = normalize_affected_url("\n".join(_urls(URL_LIST_MAX_COUNT)))
    assert len(normalized.split("\n")) == URL_LIST_MAX_COUNT
    assert len(normalized) > 512  # 回归：旧列长下必然溢出

    long_url = ("https://demo.example.com/" + "a" * URL_ITEM_MAX_LENGTH)[:URL_ITEM_MAX_LENGTH]
    assert len(long_url) == URL_ITEM_MAX_LENGTH
    assert normalize_affected_url(long_url) == long_url


def test_too_many_items_rejected():
    with pytest.raises(ValueError, match=f"最多 {URL_LIST_MAX_COUNT} 条"):
        normalize_affected_url("\n".join(_urls(URL_LIST_MAX_COUNT + 1)))


def test_overlong_item_rejected():
    long_url = "https://demo.example.com/" + "a" * URL_ITEM_MAX_LENGTH
    with pytest.raises(ValueError, match=f"超出上限 {URL_ITEM_MAX_LENGTH} 字符"):
        normalize_affected_url(long_url)


def test_whitespace_or_control_char_rejected():
    """条目含空格或控制字符（多为富文本/表格误粘的脏数据）直接拒绝并指出序号。"""
    with pytest.raises(ValueError, match="第 2 条影响URL 含空格或非法字符"):
        normalize_affected_url("https://a.com/1\nhttps://a.com/2 描述")
    with pytest.raises(ValueError, match="第 1 条影响URL 含空格或非法字符"):
        normalize_affected_url("https://a.com/1\x0bhttps://a.com/2")
    with pytest.raises(ValueError, match="含空格或非法字符"):
        normalize_affected_url("https://a.com/1\thttps://a.com/2")


def test_semicolon_inside_query_is_split():
    """固定口径：分号一律视为分隔符（含查询串内的分号），前后端行为一致。"""
    assert normalize_affected_url("https://a.com/x?a=1;b=2") == "https://a.com/x?a=1\nb=2"


def test_vul_in_uses_shared_normalization():
    """漏洞录入 schema 走同一口径；超限转为 ValidationError（FastAPI → 422 可读文案）。"""
    assert VulIn(title="t", affected_url="https://a.com/1;https://a.com/2").affected_url == (
        "https://a.com/1\nhttps://a.com/2"
    )
    with pytest.raises(ValidationError, match="最多 100 条"):
        VulIn(title="t", affected_url="\n".join(_urls(URL_LIST_MAX_COUNT + 1)))


def test_import_record_update_optional_passthrough():
    """导入结果修正：None 表示「本次不修改」，直通不校验；给值则同口径。"""
    assert ImportRecordUpdateIn().affected_url is None
    assert ImportRecordUpdateIn(affected_url=None).affected_url is None
    assert ImportRecordUpdateIn(affected_url="https://a.com/1；https://a.com/2").affected_url == (
        "https://a.com/1\nhttps://a.com/2"
    )
    with pytest.raises(ValidationError):
        ImportRecordUpdateIn(affected_url="https://a.com/1 描述")


def test_spring_action_drafts_use_shared_normalization():
    """春耕行动/远程检测草稿经 create_draft_vulns 写同一列，须同口径把关。"""
    for model in (SpringActionVulDraft, RemoteTestingVulDraft):
        assert model(title="t", affected_url="https://a.com/1;https://a.com/2").affected_url == (
            "https://a.com/1\nhttps://a.com/2"
        )
        with pytest.raises(ValidationError, match="含空格或非法字符"):
            model(title="t", affected_url="https://a.com/1 bad")


def test_vul_out_skips_write_validation():
    """输出模型不跑写入校验：存量脏数据（空格/超限）不应让列表与详情接口 500。"""
    legacy = "https://a.com/1 https://a.com/2"
    out = VulOut.model_validate({"id": 1, "title": "历史漏洞", "affected_url": legacy})
    assert out.affected_url == legacy

    huge = "\n".join(_urls(URL_LIST_MAX_COUNT + 5))
    out = VulOut.model_validate({"id": 2, "title": "历史长URL", "affected_url": huge})
    assert out.affected_url == huge
