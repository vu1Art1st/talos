"""P2-1 API 集成：部门 scope 覆盖列表、详情、搜索，并禁止猜测 ID 越权。"""
import pytest
from httpx import AsyncClient

from _helpers import _login_ready

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_department_scope_filters_assets_vulns_and_search(
    client: AsyncClient, auth: dict,
):
    group_a = (await client.post(
        "/api/v1/groups", headers=auth, json={"name": "Scope部门A", "remark": ""},
    )).json()
    group_b = (await client.post(
        "/api/v1/groups", headers=auth, json={"name": "Scope部门B", "remark": ""},
    )).json()
    role = (await client.post(
        "/api/v1/roles",
        headers=auth,
        json={
            "name": "Scope部门角色",
            "permissions": ["asset:manage", "vuln:manage", "special:manage"],
            "data_scope": "department",
            "remark": "",
        },
    )).json()

    scoped_user = await client.post(
        "/api/v1/users",
        headers=auth,
        json={
            "username": "scope_dept_user",
            "password": "Scope@123456",
            "realname": "部门用户",
            "role_id": role["id"],
            "group_ids": [group_a["id"]],
            "is_active": True,
        },
    )
    assert scoped_user.status_code == 200, scoped_user.text
    assert scoped_user.json()["group_ids"] == [group_a["id"]]
    scoped_auth = await _login_ready(client, "scope_dept_user", "Scope@123456")

    asset_a = (await client.post(
        "/api/v1/assets",
        headers=auth,
        json={"name": "Scope可见系统A", "group_id": group_a["id"], "department": group_a["name"]},
    )).json()
    asset_b = (await client.post(
        "/api/v1/assets",
        headers=auth,
        json={"name": "Scope隐藏系统B", "group_id": group_b["id"], "department": group_b["name"]},
    )).json()
    image = await client.post(
        "/api/v1/upload/image",
        headers=auth,
        files={"file": ("scope.png", b"\x89PNG\r\n\x1a\nscope-image", "image/png")},
    )
    assert image.status_code == 200, image.text
    image_name = image.json()["url"].rsplit("/", 1)[-1]
    vuln_a = (await client.post(
        "/api/v1/vulns/batch",
        headers=auth,
        json={
            "asset_ids": [asset_a["id"]],
            "vulns": [{"title": "ScopeVisibleVulnA", "level": 20, "vul_type": 10}],
        },
    )).json()[0]
    vuln_b = (await client.post(
        "/api/v1/vulns/batch",
        headers=auth,
        json={
            "asset_ids": [asset_b["id"]],
            "vulns": [{
                "title": "ScopeHiddenVulnB",
                "level": 20,
                "vul_type": 10,
                "description_html": f'<p><img src="/storage/uploads/images/{image_name}"></p>',
            }],
        },
    )).json()[0]

    assets = await client.get(
        "/api/v1/assets", headers=scoped_auth, params={"search": "Scope", "size": 100},
    )
    assert assets.status_code == 200, assets.text
    assert [row["id"] for row in assets.json()["items"]] == [asset_a["id"]]

    vulns = await client.get(
        "/api/v1/vulns", headers=scoped_auth, params={"search": "Scope", "size": 100},
    )
    assert vulns.status_code == 200, vulns.text
    assert [row["id"] for row in vulns.json()["items"]] == [vuln_a["id"]]

    search = await client.get(
        "/api/v1/search", headers=scoped_auth, params={"q": "Scope", "limit": 10},
    )
    assert search.status_code == 200, search.text
    assert [row["id"] for row in search.json()["assets"]] == [asset_a["id"]]
    assert [row["id"] for row in search.json()["vulns"]] == [vuln_a["id"]]

    assert (await client.get(
        f"/api/v1/assets/{asset_b['id']}", headers=scoped_auth,
    )).status_code == 404
    assert (await client.get(
        f"/api/v1/vulns/{vuln_b['id']}", headers=scoped_auth,
    )).status_code == 404
    assert (await client.get(
        f"/storage/uploads/images/{image_name}", headers=scoped_auth,
    )).status_code == 404
    assert (await client.get(
        f"/storage/uploads/images/{image_name}", headers=auth,
    )).status_code == 200
