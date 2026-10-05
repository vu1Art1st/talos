"""存量资产组织关联回填脚本测试。"""
import pytest
from sqlalchemy import select

from app.db import async_session_maker
from app.models import Asset, Group, GroupMember
from scripts.backfill_asset_groups import backfill

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_backfill_asset_groups_dry_run_and_apply(client):
    async with async_session_maker() as session:
        group = Group(name="回填资产部", remark="")
        session.add(group)
        await session.flush()
        matched = Asset(
            name="回填命中资产", department="回填资产部",
            owners=[{"name": "回填负责人", "phone": "13800009999", "email": "backfill@example.com"}],
        )
        missing = Asset(
            name="回填缺失资产", department="回填新部门",
            owners=[{"name": "回填新人", "phone": "", "email": ""}],
        )
        session.add_all([matched, missing])
        await session.commit()
        matched_id, missing_id, group_id = matched.id, missing.id, group.id

    # dry-run：只统计，不落库
    async with async_session_maker() as session:
        summary = await backfill(
            session, apply=False, create_missing=False, asset_ids=[matched_id, missing_id],
        )
    assert summary["linked"] == 1
    assert summary["added_members"] == 1
    assert [item["asset_id"] for item in summary["unmatched"]] == [missing_id]
    async with async_session_maker() as session:
        assert (await session.get(Asset, matched_id)).group_id is None
        names = (
            await session.execute(select(GroupMember.name).where(GroupMember.group_id == group_id))
        ).scalars().all()
        assert names == []

    # apply（不创建缺失组织）：命中资产关联并同步成员，缺失资产保持原样
    async with async_session_maker() as session:
        summary = await backfill(
            session, apply=True, create_missing=False, asset_ids=[matched_id, missing_id],
        )
    assert summary["linked"] == 1
    assert summary["added_members"] == 1
    async with async_session_maker() as session:
        assert (await session.get(Asset, matched_id)).group_id == group_id
        assert (await session.get(Asset, missing_id)).group_id is None
        member = (
            await session.execute(select(GroupMember).where(GroupMember.group_id == group_id))
        ).scalars().one()
        assert member.name == "回填负责人"

    # apply + create_missing：补齐缺失组织并再次关联
    async with async_session_maker() as session:
        summary = await backfill(
            session, apply=True, create_missing=True, asset_ids=[missing_id],
        )
    assert summary["linked"] == 1
    assert summary["created_groups"] == ["回填新部门"]
    async with async_session_maker() as session:
        missing = await session.get(Asset, missing_id)
        assert missing.group_id is not None
        assert missing.department == "回填新部门"
        new_group = (
            await session.execute(select(Group).where(Group.name == "回填新部门"))
        ).scalar_one()
        member = (
            await session.execute(select(GroupMember).where(GroupMember.group_id == new_group.id))
        ).scalars().one()
        assert member.name == "回填新人"
