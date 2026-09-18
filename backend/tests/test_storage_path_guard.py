"""附件路径守卫测试（安全审计 TALOS-2026-001/002 修复回归）。

覆盖：
- 白名单口径 `is_attachment_path` / 写入侧 `require_attachment_path`（400）；
- 读取侧 `resolve_storage_path` 的越界拒绝（穿越、绝对路径、盘符、不存在）与合法解析；
- 接口级：越界路径无法创建记录；存量非法路径下载 404 且**删除记录不会删除越界文件**；
- 功能不回归：合法上传路径可正常创建并下载。
"""
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.storage import is_attachment_path, require_attachment_path, resolve_storage_path
from app.db import async_session_maker
from app.models import RemoteTesting, SpringAction

HEX32 = "0123456789abcdef0123456789abcdef"
SPRING_REL = f"uploads/spring_report/{HEX32}.docx"
APPEAL_REL = f"uploads/remote_appeal/{HEX32}.pdf"


# ---------- 白名单口径 ----------
def test_is_attachment_path_whitelist():
    assert is_attachment_path(SPRING_REL)
    assert is_attachment_path(SPRING_REL, subdir="spring_report")
    assert is_attachment_path(APPEAL_REL, subdir="remote_appeal")
    # 子目录不符：不得跨域复用（春耕行动附件不能填远程检测的路径）
    assert not is_attachment_path(SPRING_REL, subdir="remote_appeal")
    for bad in (
        "",
        None,
        "../../../../etc/passwd",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "//server/share/x.docx",
        "uploads/spring_report/../../../etc/passwd",
        "uploads/../uploads/spring_report/x.docx",
        "uploads/spring_report/short.docx",                     # 文件名非 32 位 uuid4
        f"uploads/spring_report/{HEX32.upper()}.docx",          # 大写十六进制非 hex 产物
        f"uploads/spring_report/{HEX32}.docx.exe",              # 双扩展名
        f"uploads/spring_report/{HEX32}.docx ",                 # 尾随空格
        f"uploads/spring_report/{HEX32}",                       # 无扩展名
    ):
        assert not is_attachment_path(bad), bad


def test_require_attachment_path_rejects_illegal():
    assert require_attachment_path("") == ""
    assert require_attachment_path(SPRING_REL, subdir="spring_report") == SPRING_REL
    with pytest.raises(HTTPException) as exc:
        require_attachment_path("../../../../etc/passwd", subdir="spring_report")
    assert exc.value.status_code == 400


# ---------- 读取侧边界 ----------
def test_resolve_storage_path_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    inside = tmp_path / SPRING_REL
    inside.parent.mkdir(parents=True)
    inside.write_bytes(b"PK\x03\x04-payload")
    outside = tmp_path.parent / "outside_canary.txt"
    outside.write_text("secret", encoding="utf-8")

    assert resolve_storage_path(SPRING_REL) == inside.resolve()
    for bad in (
        "../outside_canary.txt",
        "../../outside_canary.txt",
        str(outside),                      # 绝对路径（Windows 盘符 / POSIX 根）
        "/etc/passwd",
        "C:/Windows/win.ini",
        "",
        f"uploads/spring_report/{'f' * 32}.docx",   # 白名单格式但文件不存在
    ):
        with pytest.raises(HTTPException) as exc:
            resolve_storage_path(bad)
        assert exc.value.status_code == 404, bad


# ---------- 接口级：写入侧拒绝越界路径 ----------
@pytest.mark.parametrize("bad", [
    "../../../../etc/passwd",
    "/etc/passwd",
    "C:/Windows/win.ini",
    "uploads/spring_report/../../../etc/passwd",
])
async def test_spring_action_rejects_illegal_attachment_path(client, auth, bad):
    resp = await client.post(
        "/api/v1/spring-actions",
        headers=auth,
        json={
            "report_no": "SEC-AUDIT", "system_name": "审计用例",
            "report_file_name": "x.docx", "report_file_path": bad,
        },
    )
    assert resp.status_code == 400, resp.text
    assert "附件路径非法" in resp.json()["detail"]


async def test_remote_testing_rejects_illegal_attachment_path(client, auth):
    resp = await client.post(
        "/api/v1/remote-testings",
        headers=auth,
        json={"system_name": "审计用例", "appeal_file_name": "c.txt", "appeal_file_path": "/etc/passwd"},
    )
    assert resp.status_code == 400, resp.text


# ---------- 功能不回归：合法附件可创建并下载 ----------
async def test_valid_attachment_roundtrip(client, auth, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    rel = f"uploads/spring_report/{'b' * 32}.docx"
    target = tmp_path / rel
    target.parent.mkdir(parents=True)
    target.write_bytes(b"PK\x03\x04-valid-attachment")

    created = await client.post(
        "/api/v1/spring-actions",
        headers=auth,
        json={
            "report_no": "SEC-OK", "system_name": "审计用例",
            "report_file_name": "正常报告.docx", "report_file_path": rel,
        },
    )
    assert created.status_code == 200, created.text
    row_id = created.json()["id"]

    downloaded = await client.get(f"/api/v1/spring-actions/{row_id}/report", headers=auth)
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == b"PK\x03\x04-valid-attachment"

    removed = await client.delete(f"/api/v1/spring-actions/{row_id}", headers=auth)
    assert removed.status_code == 200, removed.text


# ---------- 存量脏数据：下载 404 且删除不越界删文件 ----------
async def test_legacy_illegal_path_download_404(client, auth, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    canary = tmp_path.parent / "legacy_download_canary.txt"
    canary.write_text("secret", encoding="utf-8")

    async with async_session_maker() as session:
        row = SpringAction(
            report_no="SEC-LEGACY", system_name="存量脏数据",
            report_file_name="x.docx", report_file_path=str(canary),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        row_id = row.id

    resp = await client.get(f"/api/v1/spring-actions/{row_id}/report", headers=auth)
    assert resp.status_code == 404, resp.text
    assert "secret" not in resp.text


async def test_legacy_illegal_path_not_deleted(client, auth, tmp_path, monkeypatch):
    """回归 TALOS-2026-002：删除记录时不得删除越界路径指向的文件。"""
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    canary = tmp_path.parent / "legacy_delete_canary.txt"
    canary.write_text("secret", encoding="utf-8")

    async with async_session_maker() as session:
        row = RemoteTesting(
            system_name="存量脏数据", appeal_file_name="c.txt", appeal_file_path=str(canary),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        row_id = row.id

    resp = await client.delete(f"/api/v1/remote-testings/{row_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    assert canary.exists(), "越界路径指向的文件不应被删除"
    assert canary.read_text(encoding="utf-8") == "secret"


async def test_legacy_illegal_path_truncated_on_replace(
    client, auth, tmp_path, monkeypatch,
):
    """替换附件时清理旧文件同样受限：旧路径越界则跳过删除（不报错、不越界）。"""
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    canary = tmp_path.parent / "legacy_replace_canary.txt"
    canary.write_text("secret", encoding="utf-8")
    good_rel = f"uploads/remote_appeal/{'c' * 32}.pdf"
    good = tmp_path / good_rel
    good.parent.mkdir(parents=True)
    good.write_bytes(b"%PDF-1.4 valid")

    async with async_session_maker() as session:
        row = RemoteTesting(
            system_name="存量脏数据", appeal_file_name="c.txt", appeal_file_path=str(canary),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        row_id = row.id

    resp = await client.put(
        f"/api/v1/remote-testings/{row_id}",
        headers=auth,
        json={"system_name": "存量脏数据", "appeal_file_name": "n.pdf", "appeal_file_path": good_rel},
    )
    assert resp.status_code == 200, resp.text
    assert canary.exists(), "旧路径越界时不得删除该文件"
    assert Path(good).exists()


# ---------- 专项域审计补齐（附件下载留痕） ----------
async def test_attachment_download_audited(client, auth, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    rel = f"uploads/spring_report/{'d' * 32}.docx"
    target = tmp_path / rel
    target.parent.mkdir(parents=True)
    target.write_bytes(b"PK\x03\x04-audit")

    created = await client.post(
        "/api/v1/spring-actions",
        headers=auth,
        json={
            "report_no": "SEC-AUDIT-LOG", "system_name": "审计用例",
            "report_file_name": "a.docx", "report_file_path": rel,
        },
    )
    row_id = created.json()["id"]
    assert (await client.get(f"/api/v1/spring-actions/{row_id}/report", headers=auth)).status_code == 200

    logs = await client.get(
        "/api/v1/audit/logs", headers=auth,
        params={"category": "operation", "action": "attachment_download"},
    )
    assert logs.status_code == 200, logs.text
    details = [item["detail"] for item in logs.json()["items"]]
    assert any(f"spring-actions/{row_id}" in d for d in details), details

    await client.delete(f"/api/v1/spring-actions/{row_id}", headers=auth)
