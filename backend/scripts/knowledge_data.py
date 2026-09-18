"""漏洞模板库数据源加载（唯一实现）。

`knowledge-import-vulnerabilities.json` 是漏洞模板库的唯一权威数据源（135 条，部分含 CVE），
本模块把它加载为元组视图供各脚本复用：

- `scripts/seed_dev_data`：开发种子数据写入知识库；
- 正式环境同步模板库请用 `scripts.sync_knowledge_templates`（支持 `--dry-run` / `--prune`，
  并按 `vuln_types` 表真实码值校验）。

背景（2026-09-17 审计 M-1）：原先 `scripts/seed_knowledge` 自带一份加载实现，与
`sync_knowledge_templates` 的解析逻辑重复；加载逻辑已抽到本模块，
`seed_knowledge` 的 CLI 入口随之退役（其 upsert 能力是 `sync_knowledge_templates` 的子集）。

元组视图字段（与 `schemas.KnowledgeIn` 对齐）：
    (漏洞名称, 漏洞类型码, 危害等级码, 标准描述HTML, 危害说明HTML, 修复建议HTML, 参考链接)
"""
import json
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "knowledge-import-vulnerabilities.json"


def load_seed_data() -> list[tuple[str, int, int, str, str, str, list[str]]]:
    """从数据文件构建元组视图；文件缺失或为空时直接报错，避免静默写入空数据。"""
    items = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    if not isinstance(items, list) or not items:
        raise SystemExit(f"数据文件为空或格式非法：{DATA_FILE}")
    return [
        (
            it["vulnerability_name"],
            int(it["vul_type"]),
            int(it["severity_level"]),
            it.get("description_html") or "",
            it.get("harm_html") or "",
            it.get("solution_html") or "",
            [str(u).strip() for u in (it.get("references") or []) if str(u).strip()],
        )
        for it in items
    ]


SEED_DATA: list[tuple[str, int, int, str, str, str, list[str]]] = load_seed_data()
