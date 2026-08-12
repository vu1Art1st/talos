"""存量复测聚合标题回填：将旧格式「复测记录 N」重建为「复测记录yymmdd」（同日 -N 后缀）。

背景：_sync_vul_retest_html 仅在复测记录增/改/删时触发聚合，历史数据仍保留旧编号标题。
本脚本幂等扫描全部漏洞，仅重算 retest_html 中含有旧式编号标题（复测记录 N）的漏洞，
避免误改「报告复测处理」直接写入的 retest_html 内容。

用法（容器内 /app 目录，或 docker compose run --rm api python -m scripts.backfill_retest）：
    python -m scripts.backfill_retest
"""
import asyncio
import logging
import re
import sys
from pathlib import Path

# 静默 SQLAlchemy 调试回显，保持回填输出简洁
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.api.v1.vulns import _sync_vul_retest_html  # noqa: E402
from app.db import async_session_maker  # noqa: E402
from app.models import Vul, VulRetestRecord  # noqa: E402

# 旧式聚合标题：<strong>复测记录 1：</strong>（带序号编号）
_OLD_TITLE_RE = re.compile(r"复测记录\s*\d+\s*：")


async def main() -> None:
    async with async_session_maker() as session:
        vul_ids = (
            await session.execute(select(VulRetestRecord.vul_id).distinct())
        ).scalars().all()
        changed = 0
        for vid in vul_ids:
            vul = await session.get(Vul, vid)
            if vul is None:
                continue
            if not _OLD_TITLE_RE.search(vul.retest_html or ""):
                continue
            await _sync_vul_retest_html(session, vul)
            changed += 1
        await session.commit()
        print(f"复测聚合标题回填完成：共处理 {len(vul_ids)} 个含复测记录的漏洞，重建 {changed} 个")


if __name__ == "__main__":
    asyncio.run(main())
