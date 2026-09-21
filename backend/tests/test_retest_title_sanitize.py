"""复测记录标题 HTML 注入防护测试（安全审计 TALOS-2026-005 修复回归）。

`VulRetestRecordIn.title` 是纯文本字段（不受 `HtmlStr` 消毒覆盖），却被
`vul_service.sync_vul_retest_html` 拼进 `vul.retest_html` 的 HTML 片段。此前的实现原样拼接，
可把任意标签注入该字段（下发给前端渲染、并被报告导出链路当 HTML 解析）。

断言口径：先取「新增记录前」的 `retest_html` 作为基线，只对**本次追加的片段**断言。
原因：测试库为 session 级共享库，`retest_html` 会随用例累积历史片段（含已删除漏洞的残留），
按整串断言会受历史数据干扰。
"""
import pytest


async def _create_vuln(client, auth, title: str) -> int:
    resp = await client.post(
        "/api/v1/vulns", headers=auth,
        json={"title": title, "level": 30, "vul_type": 75},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _retest_html(client, auth, vul_id: int) -> str:
    resp = await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()["retest_html"]


@pytest.mark.parametrize("payload", [
    'end</strong></p><img src="http://127.0.0.1:8099/x.png"><p>x',
    "<script>alert(1)</script>",
    '<a href="javascript:alert(1)">点我</a>',
])
async def test_retest_title_escaped_in_retest_html(client, auth, payload):
    vul_id = await _create_vuln(client, auth, "标题注入用例")
    before = await _retest_html(client, auth, vul_id)

    created = await client.post(
        f"/api/v1/vulns/{vul_id}/retests", headers=auth,
        json={"title": payload, "content_html": "<p>复测正文</p>"},
    )
    assert created.status_code == 200, created.text

    html = await _retest_html(client, auth, vul_id)
    assert html.startswith(before)
    added = html[len(before):]
    # 注入的标签不得原样出现，须以实体形式保留文本
    assert "<script" not in added
    assert "<img" not in added
    assert 'href="javascript:' not in added
    assert "&lt;" in added
    # 富文本正文仍按 HTML 保留（不得被误转义）
    assert "<p>复测正文</p>" in added


async def test_retest_plain_title_unchanged(client, auth):
    """普通标题（无尖括号）不受影响：不引入实体、页面显示不变。"""
    vul_id = await _create_vuln(client, auth, "普通标题用例")
    before = await _retest_html(client, auth, vul_id)

    created = await client.post(
        f"/api/v1/vulns/{vul_id}/retests", headers=auth,
        json={"title": "复测记录250919", "content_html": "<p>ok</p>"},
    )
    assert created.status_code == 200, created.text

    html = await _retest_html(client, auth, vul_id)
    added = html[len(before):]
    assert "<strong>复测记录250919：</strong>" in added
    assert "&amp;" not in added and "&lt;" not in added


async def test_retest_title_update_also_escaped(client, auth):
    """编辑标题（PUT）同样转义，避免绕过创建路径。"""
    vul_id = await _create_vuln(client, auth, "标题编辑用例")
    created = await client.post(
        f"/api/v1/vulns/{vul_id}/retests", headers=auth,
        json={"title": "正常标题", "content_html": "<p>ok</p>"},
    )
    record_id = created.json()["id"]

    updated = await client.put(
        f"/api/v1/vulns/{vul_id}/retests/{record_id}", headers=auth,
        json={"title": '<img src=x onerror="alert(1)">', "content_html": "<p>ok</p>"},
    )
    assert updated.status_code == 200, updated.text

    html = await _retest_html(client, auth, vul_id)
    assert "<img" not in html
    assert "&lt;img" in html
