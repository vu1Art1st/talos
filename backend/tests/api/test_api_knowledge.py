"""API 集成测试：漏洞模板库。

漏洞模板库：CRUD 与从漏洞建模板、批量导入删除、默认排序、跨模板全局搜索（筛
选/分页/相关度/边界）、条目详情、CVSS 向量。

原 tests/test_api.py（4626 行单体）按领域拆分而来：用例源码逐字未改，
仅按领域重新归位；共享夹具见 tests/conftest.py，共享 helper 见 tests/api/_helpers.py。
"""
import pytest
from httpx import AsyncClient

from _helpers import _seed_search_entries

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_knowledge_crud_and_from_vul(client: AsyncClient, auth: dict):
    """漏洞模板库：upsert / 按类型查询 / 存为模板 / 删除。"""
    # 新建条目（vul_type=10 SQL注入类，以 meta 字典为准）
    resp = await client.post(
        "/api/v1/knowledge", headers=auth,
        json={"vulnerability_name": "SQL注入", "vul_type": 10, "severity_level": 10,
              "description_html": "<p>标准SQL注入描述</p>",
              "harm_html": "<p>可拖库</p>", "solution_html": "<p>参数化查询</p>",
              "references": ["https://owasp.org/Top10/"]},
    )
    assert resp.status_code == 200, resp.text
    entry = resp.json()
    assert entry["vulnerability_name"] == "SQL注入"
    assert entry["vul_type"] == 10
    assert entry["severity_level"] == 10
    assert entry["references"] == ["https://owasp.org/Top10/"]

    # 同名称再提交：覆盖而非新建（POST 为整体覆盖，未传字段取默认值）
    resp = await client.post(
        "/api/v1/knowledge", headers=auth,
        json={"vulnerability_name": "SQL注入", "vul_type": 10, "severity_level": 10,
              "description_html": "<p>描述V2</p>"},
    )
    assert resp.json()["id"] == entry["id"]
    assert resp.json()["description_html"] == "<p>描述V2</p>"

    # 同类型可存多条（不同名称）
    resp = await client.post(
        "/api/v1/knowledge", headers=auth,
        json={"vulnerability_name": "SQL盲注", "vul_type": 10, "severity_level": 20},
    )
    assert resp.status_code == 200, resp.text
    resp = await client.get("/api/v1/knowledge", headers=auth)
    assert len([e for e in resp.json() if e["vul_type"] == 10]) == 2

    # 按类型查询：返回列表（前端弹窗选择），危害等级最高的在前；未知类型 404
    resp = await client.get("/api/v1/knowledge/by-type/10", headers=auth)
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert items[0]["vulnerability_name"] == "SQL注入"
    resp = await client.get("/api/v1/knowledge/by-type/9999", headers=auth)
    assert resp.status_code == 200
    assert resp.json() == []

    # 未知类型/等级/空名称/非法参考链接拒绝
    resp = await client.post("/api/v1/knowledge", headers=auth,
                             json={"vulnerability_name": "x", "vul_type": 9999})
    assert resp.status_code == 400
    resp = await client.post("/api/v1/knowledge", headers=auth,
                             json={"vulnerability_name": "x", "vul_type": 10, "severity_level": 99})
    assert resp.status_code == 400
    resp = await client.post("/api/v1/knowledge", headers=auth,
                             json={"vulnerability_name": "   ", "vul_type": 10})
    assert resp.status_code == 422
    resp = await client.post("/api/v1/knowledge", headers=auth,
                             json={"vulnerability_name": "x", "vul_type": 10,
                                   "references": ["javascript:alert(1)"]})
    assert resp.status_code == 422

    # PUT 按 ID 编辑：改名、改等级；改为已存在名称被拒
    resp = await client.put(
        f"/api/v1/knowledge/{entry['id']}", headers=auth,
        json={"vulnerability_name": "SQL注入（联合查询）", "vul_type": 10, "severity_level": 20},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["vulnerability_name"] == "SQL注入（联合查询）"
    assert resp.json()["severity_level"] == 20
    resp = await client.put(
        f"/api/v1/knowledge/{entry['id']}", headers=auth,
        json={"vulnerability_name": "SQL盲注", "vul_type": 10},
    )
    assert resp.status_code == 400

    # 从已有漏洞存为模板：按标题作为名称 upsert，携带等级与描述/修复建议
    resp = await client.post(
        "/api/v1/vulns", headers=auth,
        json={"title": "知识库模板源漏洞", "level": 20, "vul_type": 10,
              "description_html": "<p>高质量描述</p>", "solution_html": "<p>高质量修复建议</p>"},
    )
    vul_id = resp.json()["id"]
    resp = await client.post(f"/api/v1/knowledge/from-vul/{vul_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    assert resp.json()["vulnerability_name"] == "知识库模板源漏洞"
    assert resp.json()["severity_level"] == 20
    assert resp.json()["description_html"] == "<p>高质量描述</p>"
    assert resp.json()["solution_html"] == "<p>高质量修复建议</p>"

    # 未登录拒绝
    resp = await client.get("/api/v1/knowledge")
    assert resp.status_code == 401

    # 删除
    resp = await client.delete(f"/api/v1/knowledge/{entry['id']}", headers=auth)
    assert resp.status_code == 200
    resp = await client.get("/api/v1/knowledge", headers=auth)
    assert entry["id"] not in [e["id"] for e in resp.json()]

async def test_knowledge_batch_import_and_delete(client: AsyncClient, auth: dict):
    """漏洞模板库：批量导入（按名称 upsert）与批量删除。"""
    items = [
        {"vulnerability_name": "批量-SSRF", "vul_type": 75, "severity_level": 20,
         "description_html": "<p>SSRF描述</p>", "references": ["https://portswigger.net/web-security/ssrf"]},
        {"vulnerability_name": "批量-垂直越权", "vul_type": 40, "severity_level": 10},
        {"vulnerability_name": "批量-弱口令", "vul_type": 65, "severity_level": 20},
    ]
    resp = await client.post("/api/v1/knowledge/batch-import", headers=auth, json={"items": items})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"created": 3, "updated": 0, "total": 3}

    # 再次导入：同名覆盖，新名新增
    items[0]["description_html"] = "<p>SSRF描述V2</p>"
    items.append({"vulnerability_name": "批量-未授权访问", "vul_type": 40, "severity_level": 20})
    resp = await client.post("/api/v1/knowledge/batch-import", headers=auth, json={"items": items})
    assert resp.json() == {"created": 1, "updated": 3, "total": 4}
    resp = await client.get("/api/v1/knowledge", headers=auth)
    batch_rows = [e for e in resp.json() if e["vulnerability_name"].startswith("批量-")]
    assert len(batch_rows) == 4
    ssrf_row = next(e for e in batch_rows if e["vulnerability_name"] == "批量-SSRF")
    assert ssrf_row["description_html"] == "<p>SSRF描述V2</p>"

    # 批内重名 / 字典码非法：整批拒绝
    resp = await client.post("/api/v1/knowledge/batch-import", headers=auth, json={"items": [
        {"vulnerability_name": "重名", "vul_type": 10}, {"vulnerability_name": "重名", "vul_type": 15},
    ]})
    assert resp.status_code == 400
    resp = await client.post("/api/v1/knowledge/batch-import", headers=auth, json={"items": [
        {"vulnerability_name": "非法类型", "vul_type": 9999},
    ]})
    assert resp.status_code == 400
    resp = await client.post("/api/v1/knowledge/batch-import", headers=auth, json={"items": []})
    assert resp.status_code == 422

    # 批量删除（含不存在的 ID，忽略）
    ids = [e["id"] for e in batch_rows]
    resp = await client.post("/api/v1/knowledge/batch-delete", headers=auth,
                             json={"ids": ids + [999999]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] == 4
    resp = await client.get("/api/v1/knowledge", headers=auth)
    assert not [e for e in resp.json() if e["vulnerability_name"].startswith("批量-")]

async def test_knowledge_default_sorting(client: AsyncClient, auth: dict):
    """知识库列表默认按 severity_level 升序为主、vul_type 升序为次。"""
    entries = [
        {"vulnerability_name": "排序模板A", "vul_type": 40, "severity_level": 30},
        {"vulnerability_name": "排序模板B", "vul_type": 20, "severity_level": 30},
        {"vulnerability_name": "排序模板C", "vul_type": 60, "severity_level": 10},
    ]
    for e in entries:
        resp = await client.post("/api/v1/knowledge", headers=auth, json=e)
        assert resp.status_code == 200, resp.text

    resp = await client.get("/api/v1/knowledge", headers=auth)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    # 主关键字 severity_level 升序，同级时 vul_type 升序
    keys = [(r["severity_level"], r["vul_type"]) for r in rows]
    assert keys == sorted(keys), keys

async def test_knowledge_global_search(client: AsyncClient, auth: dict):
    """跨模板全局搜索：不预选漏洞类型即可按名称 / CVE 编号 / 参考链接命中，并标注所属类型。"""
    await _seed_search_entries(client, auth)

    # 全局作用域（不带 vul_type）跨类型命中
    resp = await client.get(
        "/api/v1/knowledge/search", headers=auth, params={"q": "搜索用例", "size": 100},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] >= 3
    shiro = next(
        it for it in body["items"] if it["vulnerability_name"].endswith("（CVE-2099-2222）")
    )
    # 所属模板（漏洞类型）名称由服务端按 vuln_types 表解析，供结果标注与路径展示
    assert shiro["vul_type"] == 40 and shiro["vul_type_name"] == "权限绕过"
    assert shiro["matched_field"] == "name"
    assert shiro["username"]  # 维护人随结果返回
    assert shiro["update_time"]
    # 列表只返回摘要，不返回正文（正文由详情接口按需获取）
    assert "description_html" not in shiro and "solution_html" not in shiro
    assert shiro["summary"].startswith("搜索用例描述")

    # 按编号检索：CVE 编号写在名称后缀，无需预选漏洞类型
    resp = await client.get(
        "/api/v1/knowledge/search", headers=auth, params={"q": "cve-2099-1111"},
    )
    items = resp.json()["items"]
    assert [it["vulnerability_name"] for it in items] == ["搜索用例-SQL注入（CVE-2099-1111）"]

    # 参考链接命中（非名称命中）
    resp = await client.get(
        "/api/v1/knowledge/search", headers=auth, params={"q": "uniq-ref-3333"},
    )
    items = resp.json()["items"]
    assert len(items) == 1 and items[0]["matched_field"] == "references"

    # 保留原有「模板内搜索」能力：限定 vul_type 的结果集合与 by-type 完全一致
    by_type = (await client.get("/api/v1/knowledge/by-type/10", headers=auth)).json()
    scoped = (await client.get(
        "/api/v1/knowledge/search", headers=auth, params={"vul_type": 10, "size": 100},
    )).json()
    assert {e["id"] for e in by_type} == {it["id"] for it in scoped["items"]}
    assert scoped["total"] == len(by_type)

    # 未登录不可搜索
    assert (await client.get("/api/v1/knowledge/search")).status_code == 401

async def test_knowledge_search_filters_sort_paging(client: AsyncClient, auth: dict):
    """筛选（类型 / 等级 / 维护人 / 更新时间）+ 排序（相关度 / 等级）+ 分页。"""
    created = await _seed_search_entries(client, auth)
    username = created[0]["username"]

    # 漏洞类型多选
    resp = await client.get("/api/v1/knowledge/search", headers=auth,
                            params={"q": "搜索用例", "vul_type": "10,40", "size": 100})
    assert resp.status_code == 200, resp.text
    assert {it["vul_type"] for it in resp.json()["items"]} <= {10, 40}

    # 危害等级筛选
    resp = await client.get("/api/v1/knowledge/search", headers=auth,
                            params={"q": "搜索用例", "severity_level": 20, "size": 100})
    assert [it["vul_type"] for it in resp.json()["items"]] == [40]

    # 维护人筛选（存在的维护人命中 / 不存在的为空）
    assert (await client.get("/api/v1/knowledge/search", headers=auth,
                             params={"q": "搜索用例", "creator": username})).json()["total"] >= 3
    assert (await client.get("/api/v1/knowledge/search", headers=auth,
                             params={"q": "搜索用例", "creator": "不存在维护人ZZZ"})).json()["total"] == 0

    # 更新时间区间（含当日；区间外为空）
    assert (await client.get("/api/v1/knowledge/search", headers=auth,
                             params={"q": "搜索用例", "updated_from": "2020-01-01"})).json()["total"] >= 3
    assert (await client.get("/api/v1/knowledge/search", headers=auth,
                             params={"q": "搜索用例", "updated_to": "2020-01-01"})).json()["total"] == 0

    # 排序：severity_level 升序 / 降序
    resp = await client.get("/api/v1/knowledge/search", headers=auth,
                            params={"q": "搜索用例", "sort": "severity_level", "order": "asc", "size": 100})
    lv = [it["severity_level"] for it in resp.json()["items"]]
    assert lv == sorted(lv) and len(lv) >= 3
    # 非法 sort 回退默认排序（不报错）
    assert (await client.get("/api/v1/knowledge/search", headers=auth,
                             params={"q": "搜索用例", "sort": "drop table"})).status_code == 200

    # 分页：size=1 时 total 不变、items 收缩
    page1 = (await client.get("/api/v1/knowledge/search", headers=auth,
                              params={"q": "搜索用例", "size": 1, "page": 1})).json()
    page2 = (await client.get("/api/v1/knowledge/search", headers=auth,
                              params={"q": "搜索用例", "size": 1, "page": 2})).json()
    assert len(page1["items"]) == 1 and len(page2["items"]) == 1
    assert page1["total"] == page2["total"] >= 3
    assert page1["items"][0]["id"] != page2["items"][0]["id"]

async def test_knowledge_search_relevance_ranking(client: AsyncClient, auth: dict):
    """相关度排序：名称全等 > 名称前缀 > 名称包含。"""
    for name in ("搜索相关度", "搜索相关度扩展", "前置搜索相关度"):
        resp = await client.post("/api/v1/knowledge", headers=auth,
                                 json={"vulnerability_name": name, "vul_type": 75, "severity_level": 30})
        assert resp.status_code == 200, resp.text

    resp = await client.get("/api/v1/knowledge/search", headers=auth,
                            params={"q": "搜索相关度", "size": 100})
    names = [it["vulnerability_name"] for it in resp.json()["items"]]
    assert names[:3] == ["搜索相关度", "搜索相关度扩展", "前置搜索相关度"], names

async def test_knowledge_search_deep_and_edge_cases(client: AsyncClient, auth: dict):
    """正文深度搜索开关、LIKE 通配符转义与非法参数边界。"""
    await _seed_search_entries(client, auth)
    resp = await client.post(
        "/api/v1/knowledge", headers=auth,
        json={"vulnerability_name": "正文深度搜索用例", "vul_type": 75, "severity_level": 30,
              "description_html": "<p>深度搜索唯一标记XQZ 仅出现在正文中。</p>"},
    )
    assert resp.status_code == 200, resp.text

    # 默认不搜正文
    resp = await client.get("/api/v1/knowledge/search", headers=auth,
                            params={"q": "深度搜索唯一标记XQZ"})
    assert resp.json()["total"] == 0
    # deep=True 才进正文，且命中位置标注为 content
    resp = await client.get("/api/v1/knowledge/search", headers=auth,
                            params={"q": "深度搜索唯一标记XQZ", "deep": "true"})
    body = resp.json()
    assert body["total"] == 1 and body["items"][0]["matched_field"] == "content"

    # LIKE 通配符按字面处理：输入 % 不得退化为「命中全表」
    resp = await client.get("/api/v1/knowledge/search", headers=auth,
                            params={"q": "%", "size": 100})
    hit_names = [it["vulnerability_name"] for it in resp.json()["items"]]
    assert "搜索用例-SQL注入（CVE-2099-1111）" not in hit_names
    assert "搜索用例-服务器弱口令" not in hit_names

    # 未知漏洞类型码 → 空集（不报错）
    resp = await client.get("/api/v1/knowledge/search", headers=auth,
                            params={"vul_type": 999999})
    assert resp.status_code == 200 and resp.json()["total"] == 0
    # order 非法 → 422
    assert (await client.get("/api/v1/knowledge/search", headers=auth,
                             params={"order": "sideways"})).status_code == 422
    # q 超长 → 422
    assert (await client.get("/api/v1/knowledge/search", headers=auth,
                             params={"q": "x" * 100})).status_code == 422

async def test_knowledge_get_entry_detail(client: AsyncClient, auth: dict):
    """套用模板前按 ID 取完整条目：正文与 CVSS 向量齐备；不存在返回 404。"""
    created = await _seed_search_entries(client, auth)
    entry_id = created[1]["id"]
    resp = await client.get(f"/api/v1/knowledge/{entry_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["vul_type"] == 40
    assert "路径规范化不一致" in detail["description_html"]
    assert detail["cvss_vector"] == ""

    assert (await client.get("/api/v1/knowledge/999999", headers=auth)).status_code == 404

async def test_knowledge_cvss_vector(client: AsyncClient, auth: dict):
    vector = "CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H"
    resp = await client.post(
        "/api/v1/knowledge", headers=auth,
        json={"vulnerability_name": "SSRF向量模板", "vul_type": 75, "severity_level": 20, "cvss_vector": vector},
    )
    assert resp.status_code == 200, resp.text
    entry = resp.json()
    assert entry["cvss_vector"] == vector

    # from-vul：漏洞向量随「存为模板」带入知识库
    resp = await client.post(
        "/api/v1/vulns", headers=auth,
        json={"title": "存模板向量漏洞", "level": 20, "cvss_vector": vector},
    )
    vul_id = resp.json()["id"]
    resp = await client.post(f"/api/v1/knowledge/from-vul/{vul_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    assert resp.json()["cvss_vector"] == vector
