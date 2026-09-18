"""源码结构守卫：防止已修复的安全缺陷以同样形态回归。

守护三类模式（命中即失败）：
1. 附件路径裸拼接：`settings.storage_path / <数据库或请求体字段>`，或对
   `report_file_path` / `appeal_file_path` 直接做路径拼接——两者都必须经
   `app/core/storage.py::resolve_storage_path`（安全审计 TALOS-2026-001/002）；
2. `app/` 内的直接出站调用（`urlopen` / `requests.*`）：出站目标必须经
   `app/core/outbound.py` 校验，报告导出的远程图片已改为「只内嵌本地文件」
   （安全审计 TALOS-2026-003/004）；
3. 复测标题聚合入口必须转义：`sync_vul_retest_html` 内出现 `html_mod.escape`
   （安全审计 TALOS-2026-005）。

这些约定无法由类型系统或普通单测覆盖（改错是"能跑通但越界"），故用源码级守卫固化。
"""
import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"

# 规则 1a：storage_path 与附件字段出现在同一行 → 必须走 resolve_storage_path
_STORAGE_JOIN = re.compile(r"storage_path\s*/")
_ATTACHMENT_FIELDS = ("report_file_path", "appeal_file_path")
# 规则 1b：直接对「来自请求体/数据库对象」的字段做路径拼接
_EXTERNAL_FIELD_JOIN = re.compile(
    r"storage_path\s*/\s*(?:row|record|obj|body|data|item|payload)\s*[\.\[]"
)
# 规则 2：直接出站调用（httpx 走 core/outbound / 配置 URL 属受控场景，不在本规则内）
_DIRECT_OUTBOUND = re.compile(r"\b(?:urlopen|requests\.(?:get|post|put|head))\s*\(")


def _iter_py_files():
    return [p for p in APP_DIR.rglob("*.py") if "__pycache__" not in p.parts]


def _scan(pattern: re.Pattern[str], *, with_attachment_fields: bool = False) -> list[str]:
    hits: list[str] = []
    for path in _iter_py_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not pattern.search(line):
                continue
            if with_attachment_fields and not any(f in line for f in _ATTACHMENT_FIELDS):
                continue
            hits.append(f"{path.relative_to(APP_DIR)}:{lineno}: {line.strip()}")
    return hits


def test_no_raw_storage_path_join_with_attachment_field():
    hits = _scan(_STORAGE_JOIN, with_attachment_fields=True)
    assert not hits, (
        "附件路径不得直接拼接 storage_path（应改用 core.storage.resolve_storage_path）：\n"
        + "\n".join(hits)
    )


def test_no_raw_storage_path_join_with_external_field():
    hits = _scan(_EXTERNAL_FIELD_JOIN)
    assert not hits, (
        "禁止用请求体/数据库对象字段直接拼接 storage_path（越界读写风险）：\n" + "\n".join(hits)
    )


def test_no_direct_outbound_call():
    hits = _scan(_DIRECT_OUTBOUND)
    assert not hits, (
        "app/ 内不得直接使用 urlopen/requests 出站（应经 core.outbound 校验或改为本地文件）：\n"
        + "\n".join(hits)
    )


def test_retest_html_aggregation_escapes_title():
    source = (APP_DIR / "services" / "vul_service.py").read_text(encoding="utf-8")
    start = source.index("async def sync_vul_retest_html")
    body = source[start:]
    assert "html_mod.escape" in body, "复测标题聚合必须转义 title（TALOS-2026-005）"
    # 自产标题不含外部输入，但自定义 title 分支必须先转义再拼接
    assert 'html_mod.escape(r.title.strip())' in body


# ---------- 批次 E：图片鉴权 / 安全响应头的回归守卫（配置类改动，靠源码断言固化） ----------
_REPO_ROOT = APP_DIR.parent.parent


def test_images_not_served_by_static_mount():
    """图片不得回退为静态直出（批次 E-1：需登录下发）。"""
    main_src = (APP_DIR / "main.py").read_text(encoding="utf-8")
    assert "StaticFiles" not in main_src, (
        "main.py 不得再挂载 StaticFiles（图片/附件必须走鉴权接口，见 app/api/images.py）"
    )
    images_src = (APP_DIR / "api" / "images.py").read_text(encoding="utf-8")
    assert "get_image_viewer" in images_src, "图片端点必须依赖 get_image_viewer 做认证"


def test_nginx_security_headers_present():
    """前端 Nginx 必须带点击劫持/嗅探/来源等安全响应头（批次 E-2）。"""
    conf = (_REPO_ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    for header in (
        'add_header X-Frame-Options "DENY"',
        'add_header X-Content-Type-Options "nosniff"',
        "add_header Referrer-Policy",
        "add_header Permissions-Policy",
        "Content-Security-Policy",
        "server_tokens off",
    ):
        assert header in conf, f"nginx.conf 缺少安全响应头：{header}"
    # CSP 处于观察期：必须仍是 Report-Only（强制模式需同步确认前端无违规后再改）
    assert "Content-Security-Policy-Report-Only" in conf


def test_must_change_password_enforced_server_side():
    """未改密拦截必须留在依赖层（批次 E-6），不得只在前端弹框。"""
    src = (APP_DIR / "core" / "deps.py").read_text(encoding="utf-8")
    assert "_enforce_password_change" in src
    assert "X-Must-Change-Password" in src
    assert "must_change_password" in src


def test_scripts_app_references_resolve():
    """运维脚本对 app 模块的引用必须有效。

    2026-09-19 生产踩坑：`scripts/backfill_retest.py` 在批次 C 重构后仍从
    `app.api.v1.vulns` 导入已迁走的 `_sync_vul_retest_html`，脚本不参与测试收集，
    直到运维在容器里执行回填才报 ImportError。此处以静态解析固化守卫。
    """
    from scripts._check_imports import collect_problems

    problems = collect_problems()
    assert not problems, "脚本引用了不存在的模块/符号：\n" + "\n".join(problems)
