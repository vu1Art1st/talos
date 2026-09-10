"""漏洞模板库预置数据：直接读取 `knowledge-import-vulnerabilities.json`（唯一权威数据源）。

用法（backend 目录下，需项目 venv 解释器）：
    python -m scripts.seed_knowledge

数据文件为条目数组，字段与 `schemas.KnowledgeIn` 对齐：
    vulnerability_name / vul_type / severity_level /
    description_html / harm_html / solution_html / references
描述、危害与修复建议为富文本 HTML（修复建议多条时以 `<p>1、…</p>` 编号换行）。

`SEED_DATA` 对外暴露为元组视图，供 `scripts.seed_dev_data` 复用：
    (漏洞名称, 漏洞类型码, 危害等级码, 标准描述HTML, 危害说明HTML, 修复建议HTML, 参考链接)
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA_FILE = Path(__file__).resolve().parent.parent / "knowledge-import-vulnerabilities.json"


def _load_seed_data() -> list[tuple[str, int, int, str, str, str, list[str]]]:
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


SEED_DATA: list[tuple[str, int, int, str, str, str, list[str]]] = _load_seed_data()


async def main() -> None:
    from sqlalchemy import select

    from app.constants import VUL_LEVEL, VUL_TYPE
    from app.core.sanitize import sanitize_html
    from app.db import async_session_maker, init_db
    from app.models import KnowledgeEntry
    from app.models.user import User

    await init_db()

    # 校验字典码，避免录入非法数据
    for name, vt, sl, *_ in SEED_DATA:
        assert vt in VUL_TYPE, f"{name}: 非法漏洞类型 {vt}"
        assert sl in VUL_LEVEL, f"{name}: 非法危害等级 {sl}"

    async with async_session_maker() as session:
        admin = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none()
        creator_id = admin.id if admin else None
        username = (admin.realname or admin.username) if admin else "system"

        existing = {
            e.vulnerability_name: e
            for e in (await session.execute(select(KnowledgeEntry))).scalars().all()
        }
        created = updated = 0
        for name, vt, sl, desc_html, harm_html, sol_html, refs in SEED_DATA:
            entry = existing.get(name)
            if entry is None:
                entry = KnowledgeEntry(vulnerability_name=name)
                session.add(entry)
                created += 1
            else:
                updated += 1
            entry.vul_type = vt
            entry.severity_level = sl
            entry.description_html = sanitize_html(desc_html)
            entry.harm_html = sanitize_html(harm_html)
            entry.solution_html = sanitize_html(sol_html)
            entry.references = list(refs)
            entry.creator_id = creator_id
            entry.username = username
        await session.commit()

    print(f"知识库预置完成：新增 {created} 条，更新 {updated} 条，共 {len(SEED_DATA)} 条。")


if __name__ == "__main__":
    asyncio.run(main())
