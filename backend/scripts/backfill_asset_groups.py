"""存量资产的组织关联回填：补齐 `assets.group_id` 并把负责人同步到组织成员。

背景：资产负责人同步曾以部门名字符串为唯一关联，部门后建或改名时不会回填，
导致 `assets.group_id` 长期为空、负责人未进入组织。本脚本按组织名精确匹配
（忽略首尾空白）回填 `group_id` 并同步成员；是否创建缺失组织由显式开关控制。

用法（backend/ 目录，或容器内 /app）：
    python -m scripts.backfill_asset_groups --dry-run                 # 默认，仅统计
    python -m scripts.backfill_asset_groups --apply                   # 回填已存在的组织
    python -m scripts.backfill_asset_groups --apply --create-missing  # 同时创建缺失组织
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._common import ensure_local_env, save_backup  # noqa: E402

# 必须在导入 app.db（模块级实例化 Settings）之前补齐根 .env 与开发库 DSN
ensure_local_env()

from sqlalchemy import select  # noqa: E402

from app.db import async_session_maker  # noqa: E402
from app.models import Asset, GroupMember  # noqa: E402
from app.services.org_service import (  # noqa: E402
    ensure_group,
    find_group_by_name,
    sync_owners_to_group_members,
)


async def backfill(
    session,
    *,
    apply: bool = False,
    create_missing: bool = False,
    asset_ids: list[int] | None = None,
) -> dict:
    """执行回填，返回统计结果；apply=False 时统计后回滚。"""
    stmt = select(Asset).where(Asset.group_id.is_(None), Asset.department != "")
    if asset_ids:
        stmt = stmt.where(Asset.id.in_(asset_ids))
    assets = (await session.execute(stmt.order_by(Asset.id))).scalars().all()
    linked = 0
    added_members = 0
    created_groups: list[str] = []
    unmatched: list[dict] = []
    snapshots: list[dict] = []
    existing_names: dict[int, set[str]] = {}

    for asset in assets:
        department = (asset.department or "").strip()
        group = await find_group_by_name(session, department)
        if group is None and create_missing:
            group, created = await ensure_group(session, department)
            if created:
                created_groups.append(group.name)
        if group is None:
            unmatched.append({"asset_id": asset.id, "department": department})
            continue

        linked += 1
        snapshots.append({
            "asset_id": asset.id,
            "old_department": asset.department,
            "new_department": group.name,
            "new_group_id": group.id,
        })
        if apply:
            asset.group_id = group.id
            asset.department = group.name
            added_members += await sync_owners_to_group_members(
                session, group.id, list(asset.owners or []),
            )
        else:
            if group.id not in existing_names:
                existing_names[group.id] = set(
                    (
                        await session.execute(
                            select(GroupMember.name).where(GroupMember.group_id == group.id)
                        )
                    ).scalars().all()
                )
            for owner in (asset.owners or []):
                name = (owner.get("name") or "").strip()
                if name and name not in existing_names[group.id]:
                    existing_names[group.id].add(name)
                    added_members += 1

    if not apply:
        await session.rollback()
        print(
            f"[dry-run] 可关联资产 {linked} 条，可新增成员 {added_members} 条；"
            f"待创建组织 {len(created_groups)} 个；未匹配部门 {len(unmatched)} 条（未落库）"
        )
    else:
        backup_file = save_backup(snapshots, "asset_groups")
        await session.commit()
        print(
            f"回填完成：关联资产 {linked} 条，新增成员 {added_members} 条，"
            f"新建组织 {len(created_groups)} 个，未匹配部门 {len(unmatched)} 条"
        )
        if backup_file:
            print(f"原值备份：{backup_file}")
    if unmatched:
        for item in unmatched[:50]:
            print(f"  未匹配：资产#{item['asset_id']} 部门「{item['department']}」")
        if len(unmatched) > 50:
            print(f"  ...其余 {len(unmatched) - 50} 条省略")
    return {
        "linked": linked,
        "added_members": added_members,
        "created_groups": created_groups,
        "unmatched": unmatched,
    }


async def main(
    apply: bool = False,
    create_missing: bool = False,
    asset_ids: list[int] | None = None,
) -> None:
    async with async_session_maker() as session:
        await backfill(
            session, apply=apply, create_missing=create_missing, asset_ids=asset_ids,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="回填资产的组织关联与负责人成员")
    parser.add_argument("--dry-run", action="store_true", help="仅统计不落库（默认；显式指定以对齐仓库习惯）")
    parser.add_argument("--apply", action="store_true", help="真正落库；缺省为 dry-run")
    parser.add_argument("--create-missing", action="store_true", help="为未匹配部门创建组织")
    parser.add_argument("--asset-id", action="append", type=int, default=None, help="只处理指定资产（可重复）")
    args = parser.parse_args()
    # argparse 在 asyncio.run 之前解析，避免把事件循环参数与脚本参数混用
    import asyncio  # noqa: E402

    asyncio.run(main(
        apply=args.apply and not args.dry_run,
        create_missing=args.create_missing,
        asset_ids=args.asset_id,
    ))
