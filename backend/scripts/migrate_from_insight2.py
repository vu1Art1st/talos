#!/usr/bin/env python
"""洞察2.0 -> 新平台数据迁移脚本。

用法（在 backend 目录下）:
    python scripts/migrate_from_insight2.py \
        --mysql-host 127.0.0.1 --mysql-port 3306 \
        --mysql-user root --mysql-pass xxx --mysql-db insight2

说明：
- 迁移 用户/组/应用/资产/漏洞/漏洞日志；角色映射到内置角色。
- 旧库密码为明文，迁移后统一重置为随机不可用密码并标记 must_change_password，
  用户需通过管理员重置后登录。
- 旧漏洞的 vul_poc_html / vul_solution_html 直接作为新平台富文本初值。
"""
import argparse
import asyncio
import secrets
import sys
from datetime import datetime
from pathlib import Path

import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.core.timeutil import now  # noqa: E402
from app.db import async_session_maker, init_db  # noqa: E402
from app.models import App, Asset, Group, Role, User, Vul, VulLog  # noqa: E402


def ts(value) -> datetime | None:
    """旧库使用 epoch 秒（Double），0 表示未发生。"""
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        return None
    return datetime.utcfromtimestamp(value) if value > 0 else None


def fetch_all(conn, sql: str) -> list[dict]:
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute(sql)
        return cursor.fetchall()


async def migrate(args) -> None:
    conn = pymysql.connect(
        host=args.mysql_host, port=args.mysql_port,
        user=args.mysql_user, password=args.mysql_pass,
        database=args.mysql_db, charset="utf8mb4",
    )

    await init_db()

    async with async_session_maker() as session:
        default_role = (
            await session.execute(select(Role).where(Role.name == "安全工程师"))
        ).scalar_one()

        # ---- 用户 ----
        old_users = fetch_all(conn, "select * from user")
        user_map: dict[int, int] = {}
        for ou in old_users:
            username = ou.get("username") or f"user{ou['id']}"
            exists = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one_or_none()
            if exists:
                user_map[ou["id"]] = exists.id
                continue
            user = User(
                username=username,
                # 旧库明文密码不迁移：置随机密码并强制重置
                password_hash=hash_password(secrets.token_urlsafe(16)),
                realname=ou.get("realname") or "",
                email=ou.get("email") or "",
                phone=ou.get("phone") or "",
                role_id=default_role.id,
                must_change_password=True,
            )
            session.add(user)
            await session.flush()
            user_map[ou["id"]] = user.id
        print(f"用户迁移完成: {len(old_users)}")

        # ---- 组 ----
        old_groups = fetch_all(conn, "select * from `group`")
        group_map: dict[int, int] = {}
        for og in old_groups:
            group = Group(name=og.get("name") or f"组{og['id']}", remark=og.get("remark") or "")
            session.add(group)
            await session.flush()
            group_map[og["id"]] = group.id
        print(f"组迁移完成: {len(old_groups)}")

        # ---- 应用 ----
        old_apps = fetch_all(conn, "select * from app")
        app_map: dict[int, int] = {}
        for oa in old_apps:
            app = App(
                name=oa.get("name") or f"应用{oa['id']}",
                url=oa.get("url") or "",
                app_type=int(oa.get("type") or 20),
                sec_level=int(oa.get("sec_level") or 40),
                status=int(oa.get("status") or 10),
                group_id=group_map.get(oa.get("group_id")),
                owner_id=user_map.get(oa.get("user_id")),
                remark=oa.get("remark") or "",
            )
            session.add(app)
            await session.flush()
            app_map[oa["id"]] = app.id
        print(f"应用迁移完成: {len(old_apps)}")

        # ---- 资产 ----
        old_assets = fetch_all(conn, "select * from asset")
        for oas in old_assets:
            session.add(Asset(
                value=oas.get("value") or "",
                asset_type=int(oas.get("type") or 10),
                is_open=bool(int(oas.get("is_open") or 0)),
                is_https=bool(int(oas.get("is_https") or 0)),
                remark="",
            ))
        print(f"资产迁移完成: {len(old_assets)}")

        # ---- 漏洞 ----
        old_vuls = fetch_all(conn, "select * from vul")
        vul_map: dict[int, int] = {}
        for ov in old_vuls:
            vul = Vul(
                title=ov.get("vul_name") or f"漏洞{ov['id']}",
                vul_type=int(ov.get("vul_type") or 75),
                level=int(ov.get("vul_level") or 30),
                status=int(ov.get("vul_status") or 10),
                source=int(ov.get("vul_source") or 10),
                layer=int(ov.get("layer") or 10),
                description_html=ov.get("vul_poc_html") or "",
                solution_html=ov.get("vul_solution_html") or "",
                score=int(ov.get("score") or 0),
                risk_score=int(ov.get("risk_score") or 0),
                left_risk_score=int(ov.get("left_risk_score") or 0),
                asset_level=int(ov.get("asset_level") or 0),
                is_retest=bool(int(ov.get("is_retest") or 0)),
                delay_days=int(ov.get("delay_days") or 0),
                delay_reason=ov.get("delay_reason") or "",
                app_id=app_map.get(ov.get("app_id")),
                submitter_id=user_map.get(ov.get("user_id")),
                submit_time=ts(ov.get("submit_time")) or now(),
                audit_time=ts(ov.get("audit_time")),
                notice_time=ts(ov.get("notice_time")),
                fix_time=ts(ov.get("fix_time")),
            )
            session.add(vul)
            await session.flush()
            vul_map[ov["id"]] = vul.id
        print(f"漏洞迁移完成: {len(old_vuls)}")

        # ---- 漏洞日志 ----
        old_logs = fetch_all(conn, "select * from vullog")
        migrated_logs = 0
        for ol in old_logs:
            new_vul_id = vul_map.get(ol.get("vul_id"))
            if not new_vul_id:
                continue
            session.add(VulLog(
                vul_id=new_vul_id,
                user_id=user_map.get(ol.get("user_id")),
                username=ol.get("username") or "",
                action=ol.get("action") or "",
                content=ol.get("content") or "",
                create_time=ts(ol.get("create_time")) or now(),
            ))
            migrated_logs += 1
        print(f"漏洞日志迁移完成: {migrated_logs}")

        await session.commit()
    conn.close()
    print("全部迁移完成。旧用户密码已重置，请管理员为用户重新设置密码。")


def main() -> None:
    parser = argparse.ArgumentParser(description="洞察2.0 数据迁移")
    parser.add_argument("--mysql-host", default="127.0.0.1")
    parser.add_argument("--mysql-port", type=int, default=3306)
    parser.add_argument("--mysql-user", default="root")
    parser.add_argument("--mysql-pass", default="")
    parser.add_argument("--mysql-db", default="insight2")
    asyncio.run(migrate(parser.parse_args()))


if __name__ == "__main__":
    main()
