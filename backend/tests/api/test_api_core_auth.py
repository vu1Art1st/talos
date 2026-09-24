"""API 集成测试：健康检查 / 认证 / 元数据字典 / 权限目录 / 用户组。

健康检查 / 认证 / 元数据字典 / 权限目录 / 用户组。

原 tests/test_api.py（4626 行单体）按领域拆分而来：用例源码逐字未改，
仅按领域重新归位；共享夹具见 tests/conftest.py，共享 helper 见 tests/api/_helpers.py。
"""
import pytest
from httpx import AsyncClient

from _helpers import _login_ready

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_health(client: AsyncClient):
    resp = await client.get("/api/health")
    assert resp.status_code == 200

async def test_login_and_me(client: AsyncClient, auth: dict):
    resp = await client.get("/api/v1/auth/me", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "admin"

    bad = await client.post(
        "/api/v1/auth/login", data={"username": "admin", "password": "wrong"}
    )
    assert bad.status_code == 401

async def test_meta(client: AsyncClient, auth: dict):
    resp = await client.get("/api/v1/meta", headers=auth)
    assert resp.status_code == 200
    meta = resp.json()
    assert "vul_level" in meta and "vul_status" in meta
    # 字典单源：色值命名空间、导入/导出状态与 nonpen 命名空间随 /meta 下发
    assert meta["colors"]["vul_level"]["10"] == "#DC2626"
    assert meta["import_batch_status"]["parsed"] == "待确认"
    assert meta["export_job_status"]["done"] == "已完成"
    # 报告「草稿/已定稿」状态功能已取消：名称与色值字典不再随 /meta 下发
    assert "report_status" not in meta
    assert "report_status" not in meta["colors"]
    # 名称字典对应的色值必须同步下发：前端 applyDictMeta 无条件注入，
    # 任一 key 缺失会令导出/导入状态标签渲染崩溃（报告区域整体消失）
    assert meta["colors"]["import_batch_status"]["parsed"] == "#0284C7"
    assert meta["colors"]["import_record_status"]["confirmed"] == "#059669"
    assert meta["colors"]["export_job_status"]["done"] == "#059669"
    nonpen_items = {item["key"] for item in meta["nonpen"]["items"]}
    assert nonpen_items == {"baseline", "host", "web"}
    assert meta["nonpen"]["actions"]["not_started"] == ["start", "ignore"]
    assert meta["nonpen"]["action_names"]["start"] == "开始初测"
    # 漏扫测试项状态与渗透工单统一口径（2026-09-16 改名）
    assert meta["nonpen"]["status"]["wait_retest"] == "初测完成"

async def test_permission_denied(client: AsyncClient):
    resp = await client.get("/api/v1/vulns")
    assert resp.status_code == 401

async def test_role_permission_catalog(client: AsyncClient, auth: dict):
    """权限目录接口：按功能模块分组返回，key 与扁平 PERMISSIONS 一致。"""
    resp = await client.get("/api/v1/roles/permissions/catalog", headers=auth)
    assert resp.status_code == 200, resp.text
    groups = resp.json()
    assert isinstance(groups, list) and groups
    keys = [it["key"] for g in groups for it in g["items"]]
    assert keys == [
        "dashboard:view", "asset:manage", "vuln:submit", "vuln:audit", "vuln:manage",
        "import:manage", "report:manage", "special:manage", "user:manage", "system:manage",
    ]
    for g in groups:
        assert g["group"]
        for it in g["items"]:
            assert it["label"] and "desc" in it

    # 扁平接口保持兼容
    flat = await client.get("/api/v1/roles/permissions", headers=auth)
    assert flat.status_code == 200
    assert flat.json() == keys

async def test_dict_options(client: AsyncClient, auth: dict):
    """测试类型字典：预设种子 + 下拉新增持久化 + 重名拒绝。"""
    resp = await client.get("/api/v1/dict/test_type", headers=auth)
    assert resp.status_code == 200
    names = [o["name"] for o in resp.json()]
    assert names[:5] == ["加电上线", "互联网自主测试", "办公网自主测试", "CHBN项目测试", "品质测评"]

    # 新增：去空格后入库
    resp = await client.post("/api/v1/dict/test_type", headers=auth, json={"name": " 红蓝对抗 "})
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "红蓝对抗"

    # 重名 / 空名拒绝
    resp = await client.post("/api/v1/dict/test_type", headers=auth, json={"name": "红蓝对抗"})
    assert resp.status_code == 400
    resp = await client.post("/api/v1/dict/test_type", headers=auth, json={"name": "  "})
    assert resp.status_code == 400

    resp = await client.get("/api/v1/dict/test_type", headers=auth)
    assert "红蓝对抗" in [o["name"] for o in resp.json()]

    # 未登录拒绝
    resp = await client.get("/api/v1/dict/test_type")
    assert resp.status_code == 401

async def test_group_create_by_special_manage(client: AsyncClient, auth: dict):
    """测试计划「所属部门」下拉新增：special:manage 角色可创建组织，重名拒绝。"""
    resp = await client.post(
        "/api/v1/roles", headers=auth,
        json={"name": "专项管理角色", "permissions": ["special:manage"], "remark": ""},
    )
    role_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/users", headers=auth,
        json={"username": "special_user", "password": "Sp@123456", "realname": "专项用户",
              "email": "", "phone": "", "is_active": True, "role_id": role_id},
    )
    assert resp.status_code == 200, resp.text
    auth_sp = await _login_ready(client, "special_user", "Sp@123456")

    resp = await client.post("/api/v1/groups", headers=auth_sp, json={"name": "网络安全部", "remark": ""})
    assert resp.status_code == 200, resp.text
    resp = await client.post("/api/v1/groups", headers=auth_sp, json={"name": "网络安全部", "remark": ""})
    assert resp.status_code == 400
    resp = await client.get("/api/v1/groups", headers=auth_sp)
    assert "网络安全部" in [g["name"] for g in resp.json()]

async def test_group_owner_fields(client: AsyncClient, auth: dict):
    """组织负责人信息：改由「组织成员」管理（姓名/电话/邮箱 CRUD）。"""
    resp = await client.post(
        "/api/v1/groups", headers=auth,
        json={"name": "负责人测试部", "remark": ""},
    )
    assert resp.status_code == 200, resp.text
    group = resp.json()
    assert "owner_name" not in group  # 单字段 owner 已移除，改为组织成员承载

    # 添加组织成员
    resp = await client.post(
        f"/api/v1/groups/{group['id']}/members", headers=auth,
        json={"name": "赵六", "phone": "13700000000", "email": "zhaoliu@example.com"},
    )
    assert resp.status_code == 200, resp.text
    member = resp.json()
    assert member["name"] == "赵六"
    assert member["email"] == "zhaoliu@example.com"

    # 更新组织成员
    resp = await client.put(
        f"/api/v1/groups/{group['id']}/members/{member['id']}", headers=auth,
        json={"name": "钱七", "phone": "", "email": ""},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "钱七"
    assert resp.json()["phone"] == ""

    # 删除组织成员
    members = (await client.get(f"/api/v1/groups/{group['id']}/members", headers=auth)).json()
    assert [m["name"] for m in members] == ["钱七"]
    resp = await client.delete(
        f"/api/v1/groups/{group['id']}/members/{member['id']}", headers=auth,
    )
    assert resp.status_code == 200
    members = (await client.get(f"/api/v1/groups/{group['id']}/members", headers=auth)).json()
    assert members == []
