"""漏洞模板库同步：以 JSON 数据文件为唯一权威源，幂等地更新 knowledge_entries。

数据文件默认取仓库 backend 根目录的 `knowledge-import-vulnerabilities.json`，
按「漏洞名称」upsert（存在则整体覆盖标准描述 / 危害说明 / 修复建议 / 参考链接，不存在则新建）；
名称被优化（如补充 CVE 编号、拆分多漏洞组件）后，旧名称会残留为孤立条目，
使用 `--prune` 可一并清理「不在数据文件中」的存量条目。

用法（backend 目录下，需项目 venv 解释器）：
    python -m scripts.sync_knowledge_templates --dry-run        # 试运行，只打印差异不写库
    python -m scripts.sync_knowledge_templates                  # 同步（仅 upsert，不删条目）
    python -m scripts.sync_knowledge_templates --prune          # 同步并清理改名/合并后的残留条目

注意事项：
- 参考链接仅接受 http/https；
- 富文本字段入库前统一过 app.core.sanitize.sanitize_html 白名单消毒；
- 试运行分支不触碰 ORM 实例（避免异步会话在 rollback 后触发 MissingGreenlet）。
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.constants import VUL_LEVEL  # noqa: E402
from app.core.sanitize import sanitize_html  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = BACKEND_ROOT / "knowledge-import-vulnerabilities.json"

# 数据文件中允许出现的字段（与 schemas.KnowledgeIn 对齐）
_HTML_FIELDS = ("description_html", "harm_html", "solution_html")


def _load_items(path: Path) -> list[dict]:
    """读取并做结构校验：名称唯一、字典码在数据层可判定范围内。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise SystemExit(f"数据文件必须是非空数组：{path}")

    seen: set[str] = set()
    items: list[dict] = []
    for i, raw in enumerate(data, start=1):
        if not isinstance(raw, dict):
            raise SystemExit(f"第 {i} 条不是对象")
        name = str(raw.get("vulnerability_name", "")).strip()
        if not name:
            raise SystemExit(f"第 {i} 条缺少 vulnerability_name")
        if name in seen:
            raise SystemExit(f"漏洞名称重复：{name}")
        seen.add(name)
        if raw.get("severity_level") not in VUL_LEVEL:
            raise SystemExit(f"第 {i} 条（{name}）危害等级非法：{raw.get('severity_level')}")
        refs = raw.get("references") or []
        if not isinstance(refs, list):
            raise SystemExit(f"第 {i} 条（{name}）references 必须是数组")
        for url in refs:
            if not str(url).strip().lower().startswith(("http://", "https://")):
                raise SystemExit(f"第 {i} 条（{name}）参考链接非法：{url}")
        items.append(raw)
    return items


def _apply(entry, item: dict) -> None:
    """把数据文件条目写入 ORM 实例（不存在字段填空值，避免旧数据残留）。"""
    entry.vul_type = int(item["vul_type"])
    entry.severity_level = int(item["severity_level"])
    for field in _HTML_FIELDS:
        setattr(entry, field, sanitize_html(item.get(field) or ""))
        setattr(entry, field.replace("_html", "_json"), None)
    entry.references = [str(u).strip() for u in (item.get("references") or []) if str(u).strip()]
    entry.cvss_vector = str(item.get("cvss_vector") or "")


async def main() -> None:
    parser = argparse.ArgumentParser(description="同步漏洞模板库数据（按名称 upsert）")
    parser.add_argument("--file", default=str(DEFAULT_FILE), help="数据文件路径，默认 backend/knowledge-import-vulnerabilities.json")
    parser.add_argument("--prune", action="store_true", help="删除数据文件中不存在的存量条目（用于清理改名/合并后的残留）")
    parser.add_argument("--dry-run", action="store_true", help="仅打印差异，不写库")
    args = parser.parse_args()

    from sqlalchemy import select

    from app.db import async_session_maker, init_db
    from app.models import KnowledgeEntry, VulnType
    from app.models.user import User

    items = _load_items(Path(args.file))
    by_name = {it["vulnerability_name"]: it for it in items}

    await init_db()
    async with async_session_maker() as session:
        valid_codes = set((await session.execute(select(VulnType.code))).scalars().all())
        bad = [(it["vulnerability_name"], it["vul_type"]) for it in items if it["vul_type"] not in valid_codes]
        if bad:
            raise SystemExit("以下条目漏洞类型码不存在于 vuln_types 表：" + "、".join(f"{n}({c})" for n, c in bad))

        # 先取纯数据快照，试运行分支不触碰 ORM 实例
        existing = {
            e.vulnerability_name: e
            for e in (await session.execute(select(KnowledgeEntry))).scalars().all()
        }
        existing_names = set(existing)
        file_names = set(by_name)
        to_create = sorted(file_names - existing_names)
        to_update = sorted(file_names & existing_names)
        to_prune = sorted(existing_names - file_names) if args.prune else []

        print(f"数据文件：{args.file}")
        print(f"文件条目 {len(items)} 条 | 库内 {len(existing_names)} 条")
        print(f"  新建 {len(to_create)} 条：{'、'.join(to_create) if to_create else '无'}")
        print(f"  更新 {len(to_update)} 条")
        print(f"  清理 {len(to_prune)} 条：{'、'.join(to_prune) if to_prune else '无'}")

        if args.dry_run:
            print("\n[dry-run] 未写入数据库。")
            return

        admin = (await session.execute(select(User).where(User.username == "admin"))).scalar_one_or_none()
        creator_id = admin.id if admin else None
        username = ((admin.realname or admin.username) if admin else "system")

        for name in to_create:
            entry = KnowledgeEntry(vulnerability_name=name)
            _apply(entry, by_name[name])
            entry.creator_id = creator_id
            entry.username = username
            session.add(entry)
        for name in to_update:
            entry = existing[name]
            _apply(entry, by_name[name])
            entry.creator_id = creator_id
            entry.username = username
        for name in to_prune:
            await session.delete(existing[name])

        await session.commit()
        print(
            f"\n同步完成：新建 {len(to_create)} 条，更新 {len(to_update)} 条，"
            f"清理 {len(to_prune)} 条；当前应存 {len(file_names)} 条。"
        )


if __name__ == "__main__":
    asyncio.run(main())
