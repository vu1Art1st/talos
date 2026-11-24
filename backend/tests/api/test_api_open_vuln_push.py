"""开放 API 远程漏洞推送与 Agent 图片上传。"""
import asyncio
from io import BytesIO
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _png_bytes(color: tuple[int, int, int] = (220, 30, 30)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (16, 16), color).save(buf, format="PNG")
    return buf.getvalue()


async def _new_pat(client: AsyncClient, auth: dict, scope: str = "vuln_write") -> dict:
    resp = await client.post(
        "/api/v1/pats",
        headers=auth,
        json={"name": f"远程推送-{uuid4().hex[:8]}", "expire_days": 7, "scope": scope},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


async def _new_claimed_plan(client: AsyncClient, auth: dict) -> int:
    resp = await client.post(
        "/api/v1/testing-plans",
        headers=auth,
        json={"system_name": f"远程推送系统-{uuid4().hex[:8]}", "test_type": "渗透测试"},
    )
    assert resp.status_code == 200, resp.text
    plan_id = resp.json()["id"]
    resp = await client.post(f"/api/v1/testing-plans/{plan_id}/claim", headers=auth)
    assert resp.status_code == 200, resp.text
    return plan_id


def _push_body(source_system: str, external_id: str, image_url: str = "") -> dict:
    image_md = f"\n\n![截图]({image_url})" if image_url else ""
    return {
        "source_system": source_system,
        "items": [{
            "external_id": external_id,
            "title": "远程推送 SQL 注入",
            "level": 20,
            "vul_type": 10,
            "affected_url": "https://example.com/api/user?id=1",
            "description_md": f"## 漏洞描述\n\n存在 SQL 注入。{image_md}",
            "reproduce_md": "1. 访问接口\n2. 构造注入参数",
            "solution_md": "使用参数化查询。",
        }],
    }


async def test_open_image_upload_and_vuln_push(client: AsyncClient, auth: dict):
    plan_id = await _new_claimed_plan(client, auth)
    pat = await _new_pat(client, auth)
    source_system = f"agent-{uuid4().hex[:8]}"
    png = _png_bytes()

    image_key = f"image-{uuid4().hex}"
    image_resp = await client.post(
        f"/api/v1/open/testing-plans/{plan_id}/images",
        headers={**pat, "Idempotency-Key": image_key},
        data={"source_system": source_system, "external_image_id": "img-001"},
        files={"file": ("proof.png", png, "image/png")},
    )
    assert image_resp.status_code == 200, image_resp.text
    image = image_resp.json()
    assert image["result"] == "created"
    assert image["markdown"] == f"![漏洞截图]({image['url']})"

    duplicate_image = await client.post(
        f"/api/v1/open/testing-plans/{plan_id}/images",
        headers=pat,
        data={"source_system": source_system, "external_image_id": "img-002"},
        files={"file": ("proof.png", png, "image/png")},
    )
    assert duplicate_image.status_code == 200, duplicate_image.text
    assert duplicate_image.json()["result"] == "duplicated"
    assert duplicate_image.json()["url"] == image["url"]

    image_conflict = await client.post(
        f"/api/v1/open/testing-plans/{plan_id}/images",
        headers=pat,
        data={"source_system": source_system, "external_image_id": "img-001"},
        files={"file": ("proof.png", _png_bytes((30, 30, 220)), "image/png")},
    )
    assert image_conflict.status_code == 409

    external_id = f"vul-{uuid4().hex[:8]}"
    push_key = f"push-{uuid4().hex}"
    body = _push_body(source_system, external_id, image["url"])
    pushed = await client.post(
        f"/api/v1/open/testing-plans/{plan_id}/vulns",
        headers={**pat, "Idempotency-Key": push_key},
        json=body,
    )
    assert pushed.status_code == 200, pushed.text
    assert pushed.json()["summary"] == {"created": 1, "duplicated": 0}
    vul_id = pushed.json()["items"][0]["vul_id"]

    detail = await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)
    assert detail.status_code == 200, detail.text
    vul = detail.json()
    assert vul["testing_plan_id"] == plan_id
    assert vul["vul_type"] == 10
    assert vul["affected_url"] == "https://example.com/api/user?id=1"
    assert "<h2>漏洞描述</h2>" in vul["description_html"]
    assert image["url"] in vul["description_html"]
    assert vul["description_json"]["type"] == "doc"

    replay = await client.post(
        f"/api/v1/open/testing-plans/{plan_id}/vulns",
        headers={**pat, "Idempotency-Key": push_key},
        json=body,
    )
    assert replay.status_code == 200
    assert replay.json() == pushed.json()

    duplicate = await client.post(
        f"/api/v1/open/testing-plans/{plan_id}/vulns",
        headers=pat,
        json=body,
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["summary"] == {"created": 0, "duplicated": 1}
    assert duplicate.json()["items"][0]["vul_id"] == vul_id

    conflict_body = _push_body(source_system, external_id, image["url"])
    conflict_body["items"][0]["title"] = "内容已变化"
    conflict = await client.post(
        f"/api/v1/open/testing-plans/{plan_id}/vulns",
        headers=pat,
        json=conflict_body,
    )
    assert conflict.status_code == 409

    image_access = await client.get(image["url"], headers=pat)
    assert image_access.status_code == 200
    assert image_access.headers["content-type"].startswith("image/png")


async def test_open_vuln_push_rejects_remote_image_and_read_scope(client: AsyncClient, auth: dict):
    plan_id = await _new_claimed_plan(client, auth)
    read_pat = await _new_pat(client, auth, scope="read")
    write_pat = await _new_pat(client, auth)

    forbidden = await client.post(
        f"/api/v1/open/testing-plans/{plan_id}/vulns",
        headers=read_pat,
        json=_push_body("agent-read", f"vul-{uuid4().hex[:8]}"),
    )
    assert forbidden.status_code == 403

    remote = await client.post(
        f"/api/v1/open/testing-plans/{plan_id}/vulns",
        headers=write_pat,
        json=_push_body(
            "agent-remote",
            f"vul-{uuid4().hex[:8]}",
            "https://example.com/remote.png",
        ),
    )
    assert remote.status_code == 422
    assert "本系统上传接口" in remote.json()["detail"]


async def test_open_vuln_push_requires_core_markdown_fields(client: AsyncClient, auth: dict):
    plan_id = await _new_claimed_plan(client, auth)
    pat = await _new_pat(client, auth)
    body = _push_body("agent-required", f"vul-{uuid4().hex[:8]}")
    body["items"][0]["description_md"] = ""

    resp = await client.post(
        f"/api/v1/open/testing-plans/{plan_id}/vulns",
        headers=pat,
        json=body,
    )
    assert resp.status_code == 422


async def test_open_vuln_push_concurrent_same_external_id_is_idempotent(
    client: AsyncClient, auth: dict,
):
    plan_id = await _new_claimed_plan(client, auth)
    pat = await _new_pat(client, auth)
    body = _push_body("agent-concurrent", f"vul-{uuid4().hex[:8]}")

    first, second = await asyncio.gather(
        client.post(
            f"/api/v1/open/testing-plans/{plan_id}/vulns",
            headers={**pat, "Idempotency-Key": f"push-{uuid4().hex}"},
            json=body,
        ),
        client.post(
            f"/api/v1/open/testing-plans/{plan_id}/vulns",
            headers={**pat, "Idempotency-Key": f"push-{uuid4().hex}"},
            json=body,
        ),
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    summaries = sorted(
        (first.json()["summary"]["created"], second.json()["summary"]["created"]),
    )
    assert summaries == [0, 1]

    listed = await client.get(
        "/api/v1/open/vulns",
        headers=pat,
        params={"testing_plan_id": plan_id, "search": body["items"][0]["title"]},
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1
