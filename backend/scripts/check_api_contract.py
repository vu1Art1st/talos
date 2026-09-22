"""前后端契约检查：FastAPI OpenAPI ↔ `frontend/src/types/index.ts` 字段比对。

**为什么需要**：前端 160 个 vitest 用例全部 mock 掉 axios（`clientMockFactory`），只验证
「给定响应能否渲染」，证明不了后端真会这么答；浏览器冒烟按页面抽检，覆盖不到所有字段。
本项目已被此类漂移咬过（`ticket_id` 漏声明、`/meta` 字典键变化），且 2026-09-22 首次运行即
抓到一处真实缺陷（见下方 TS_ONLY_ALLOW 中 `NonpenPlan.asset_names` 的 TODO）。

**检查口径**（两方向的严重性刻意不同）：
- **TS 有、API 无 → 失败**：前端读取一个后端永不返回的字段，运行时静默拿到 `undefined`
  （典型：UI 块永不渲染、标签永远为空）。这是本脚本的核心价值，`el-table` 插槽的 `any` 让
  `vue-tsc` 抓不到这类问题。
- **API 有、TS 无 → 默认仅告警**：本项目 TS 类型的既定口径是「只声明前端真正消费的字段」
  （见 E-5 收敛记录），故大量 API-only 字段属**有意为之**；需要严格模式时加 `--strict`。

**边界处理**：TS 中带索引签名（`[key: string]: any`）的类型视为「开放类型」，两方向都不判定
（如 `ReportSection` 的 `content_html`/`content_json` 由索引签名承载）。

**设计取舍**：映射（TS 类型名 → OpenAPI schema 名）是人工策展的，因为两侧命名本就不一一对应
（`Vuln`→`VulOut`、`ApiToken`→`PatOut`）；已知**有意差异**登记在 allowlist 并写明理由。
脚本**不连数据库**（只读 `app.openapi()`）。

用法（backend 目录，任意环境可跑）：

    .venv/Scripts/python -m scripts.check_api_contract            # 检查（TS-only 差异则退出码 1）
    .venv/Scripts/python -m scripts.check_api_contract --strict    # 把 API-only 差异也视为失败
    .venv/Scripts/python -m scripts.check_api_contract --verbose   # 打印每个映射的字段数
"""
import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 只读 OpenAPI，不连库；但 app.core.config 在非 DEBUG 下要求强密钥，故给占位值（不参与业务）
os.environ.setdefault("VP_SECRET_KEY", "contract-check-placeholder-key-0123456789abcdef")

_FRONTEND_TYPES = Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "types" / "index.ts"

# TS 类型 → OpenAPI schema（人工策展；新增领域类型时在此登记）
MAPPING: dict[str, str] = {
    "Vuln": "VulOut",
    "VulnLog": "VulLogOut",
    "RetestRecord": "VulRetestRecordOut",
    "RetestRound": "RetestRoundOut",
    "TestingPlan": "TestingPlanOut",
    "Report": "ReportListOut",
    "ReportDetail": "ReportOut",
    "ReportSection": "SectionOut",
    "Asset": "AssetOut",
    "Group": "GroupOut",
    "GroupMember": "GroupMemberOut",
    "User": "UserOut",
    "UserBrief": "UserBrief",
    "Role": "RoleOut",
    "KnowledgeEntry": "KnowledgeOut",
    "RemoteTesting": "RemoteTestingOut",
    "SpringAction": "SpringActionOut",
    "ImportBatch": "ImportBatchOut",
    "ImportRecord": "ImportRecordOut",
    "NotifyChannel": "NotifyChannelOut",
    "ApiToken": "PatOut",
    "AuditLogEntry": "OperationLogOut",
    "ExportJob": "ExportJobOut",
    "NonpenPlan": "NonpenPlanOut",
}

# 「前端有、API 无」的有意差异（必须先确认不是缺陷；每条注明理由）
TS_ONLY_ALLOW: dict[str, set[str]] = {
    # 前端由其它接口数据聚合而得，并非 API 字段（GroupList 用成员列表算 member_count）
    "Group": {"member_count"},
    # TS 把「输入(Form) / 输出(Out)」两种形状合并进同一个实体类型：这些字段分别属 In 或纯前端表单
    # （asset_names 已于 2026-09-22 补齐到 NonpenPlanOut，故不在本清单内 —— 它现在两端都有）
    "NonpenPlan": {"status", "test_items"},
    # 计划内嵌报告 brief（OpenAPI `PlanReportBrief`）才有的字段：TS `Report` 同时复用于该形状
    "Report": {"all_closed", "is_retest", "vul_closed", "vul_total"},
    "ReportDetail": {"all_closed", "is_retest", "retest_state", "vul_closed", "vul_total"},
    # 没有任何视图消费的声明（后端不回显；可后续从 TS 清理）
    "ExportJob": {"file_name", "file_size", "version"},
    "GroupMember": {"remark"},
}

_TS_DECL = re.compile(r"^export\s+(?:interface|type)\s+(\w+)(?:\s+extends\s+(\w+))?\s*=?\s*\{")


def parse_ts_types(text: str) -> tuple[dict[str, set[str]], set[str]]:
    """解析 TS 领域类型：返回 (类型名 → 顶层字段集合, 开放类型集合)。

    开放类型 = 带索引签名（`[key: string]: any`）的类型，无法按字段集合判定，直接跳过。
    """
    lines = text.splitlines()
    fields: dict[str, set[str]] = {}
    bases: dict[str, str] = {}
    open_types: set[str] = set()
    i = 0
    while i < len(lines):
        m = _TS_DECL.match(lines[i].strip())
        if not m:
            i += 1
            continue
        name, base = m.group(1), m.group(2)
        depth = lines[i].count("{") - lines[i].count("}")
        collected: set[str] = set()
        i += 1
        while i < len(lines) and depth > 0:
            line = lines[i]
            if depth == 1:
                stripped = line.strip()
                if stripped.startswith(("[", "'", '"')):
                    # 索引签名 / 字符串字面量键 → 开放类型
                    open_types.add(name)
                elif stripped and not stripped.startswith(("//", "/*", "*", "}", "?")):
                    fm = re.match(r"^([A-Za-z_$][\w$]*)\s*\??\s*:", stripped)
                    if fm:
                        collected.add(fm.group(1))
            depth += line.count("{") - line.count("}")
            i += 1
        fields[name] = collected
        if base:
            bases[name] = base
    for name, base in bases.items():  # 并入基类字段（本项目只有一层：ReportDetail extends Report）
        if base in fields:
            fields[name] |= fields[base]
    return fields, open_types


def parse_openapi_schemas() -> dict[str, set[str]]:
    """返回 schema 名 → 字段集合；`allOf` / `$ref` 分支递归合并（pydantic 继承）。"""
    from app.main import app

    schemas = app.openapi()["components"]["schemas"]

    def props_of(name: str, seen: frozenset[str] = frozenset()) -> set[str]:
        if name in seen or name not in schemas:
            return set()
        node = schemas[name]
        props = set(node.get("properties", {}))
        for part in node.get("allOf", []):
            ref = part.get("$ref")
            if ref:
                props |= props_of(ref.rsplit("/", 1)[-1], seen | {name})
            props |= set(part.get("properties", {}))
        return props

    return {name: props_of(name) for name in schemas}


def main() -> int:
    parser = argparse.ArgumentParser(description="前后端契约检查（OpenAPI ↔ 前端 TS 类型）")
    parser.add_argument("--strict", action="store_true", help="API-only 差异也视为失败")
    parser.add_argument("--verbose", action="store_true", help="打印每个映射的字段数")
    args = parser.parse_args()

    if not _FRONTEND_TYPES.exists():
        print(f"[contract] 未找到前端类型文件：{_FRONTEND_TYPES}")
        return 1

    ts_types, open_types = parse_ts_types(_FRONTEND_TYPES.read_text(encoding="utf-8"))
    api_schemas = parse_openapi_schemas()

    failures: list[str] = []
    warnings: list[str] = []
    checked = 0
    for ts_name, api_name in sorted(MAPPING.items()):
        if ts_name not in ts_types:
            failures.append(f"{ts_name}：前端已无该类型声明（MAPPING 需同步清理）")
            continue
        if api_name not in api_schemas:
            failures.append(f"{ts_name} → {api_name}：OpenAPI 已无该 schema（MAPPING 需同步清理）")
            continue
        if ts_name in open_types:
            if args.verbose:
                print(f"  {ts_name:16s} ← {api_name:22s} 开放类型（索引签名），跳过")
            continue

        ts_fields, api_fields = ts_types[ts_name], api_schemas[api_name]
        checked += 1

        ts_only = ts_fields - api_fields - TS_ONLY_ALLOW.get(ts_name, set())
        api_only = api_fields - ts_fields
        if ts_only:
            failures.append(
                f"{ts_name}(←{api_name})：前端声明但 API 不返回 → {sorted(ts_only)}"
                "（前端会拿到 undefined；若确为有意差异请在 TS_ONLY_ALLOW 登记并写明理由）"
            )
        if api_only:
            warnings.append(f"{ts_name}(←{api_name})：API 返回但前端未声明 → {sorted(api_only)}")
        if args.verbose:
            print(f"  {ts_name:16s} ← {api_name:22s} 前端 {len(ts_fields):3d} / API {len(api_fields):3d} 字段")

    if warnings:
        level = "✗ 失败" if args.strict else "⚠ 告警"
        print(f"[contract] {level}：{len(warnings)} 组映射存在 API-only 字段（前端未声明）")
        if args.strict:
            failures.extend(warnings)
        else:
            for w in warnings:
                print(f"  - {w}")
            print("  （本项目 TS 只声明实际消费字段，API-only 多为有意为之；加 --strict 可改为失败）")

    if failures:
        print(f"[contract] ✗ 发现 {len(failures)} 处契约问题（已检查 {checked} 组映射）：")
        for p in failures:
            print(f"  - {p}")
        return 1

    print(f"[contract] ✓ 契约一致（检查 {checked} 组映射；开放类型与已登记的有意差异已跳过）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
