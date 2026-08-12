"""漏扫基线工单业务逻辑：测试项状态容器构建、状态流转、统计口径、与测试计划的联动同步。"""
import copy

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    NONPEN_ITEM_ACTIONS,
    NONPEN_ITEM_ACTION_NAMES,
    NONPEN_ITEMS,
    NONPEN_ITEM_STATUS,
)
from app.models import NonpenPlan

# 漏扫基线工单与测试计划共享的公共字段：编辑任一方时向另一方双向同步。
# 测试计划的 status/人天/漏洞统计等专属字段不被覆盖。
SYNC_FIELDS = (
    "plan_name", "system_name", "test_type", "department",
    "ticket_time", "receive_time", "ticket_id_manual",
    "asset_ids", "detail",
)


def build_items(test_items: list[str]) -> dict:
    """由勾选的测试项构造 items 容器：勾选项 not_started，未勾选项 ignored（不参与统计）。"""
    picked = set(test_items)
    return {
        key: {
            "status": "not_started" if key in picked else "ignored",
            "first_times": 0,
            "retest_times": 0,
        }
        for key in NONPEN_ITEMS
    }


def merge_items(existing: dict | None, test_items: list[str]) -> dict:
    """编辑时合并测试项勾选：仅处理勾选变化，保留未变化项的状态与次数。

    - 新勾选（原 ignored → 勾选）：置 not_started，次数清零（视为重新参与）；
    - 取消勾选（原有效 → 不勾选）：置 ignored，保留次数（与忽略口径一致，历史次数可追溯）；
    - 未变化：保持原状态与次数，不重置。
    """
    existing = existing or {}
    picked = set(test_items)
    merged = {}
    for key in NONPEN_ITEMS:
        cur = existing.get(key) or {"status": "ignored", "first_times": 0, "retest_times": 0}
        status = cur.get("status") or "ignored"
        if status == "ignored" and key in picked:
            merged[key] = {"status": "not_started", "first_times": 0, "retest_times": 0}
        elif status != "ignored" and key not in picked:
            merged[key] = {
                "status": "ignored",
                "first_times": cur.get("first_times") or 0,
                "retest_times": cur.get("retest_times") or 0,
            }
        else:
            merged[key] = {
                "status": status,
                "first_times": cur.get("first_times") or 0,
                "retest_times": cur.get("retest_times") or 0,
            }
    return merged


def apply_item_action(plan: NonpenPlan, item_key: str, action: str) -> dict:
    """执行单个测试项状态流转（按 NONPEN_ITEM_ACTIONS 白名单校验，含计数规则）。

    返回更新后的该项状态容器。
    计数规则（与演示原型一致）：
      start        not_started → testing，       first_times + 1
      done         testing → wait_retest
      direct_done  testing → retest_done（仅此状态可用，一步跳两态）
      start_retest wait_retest → retesting，     retest_times + 1
      pass         retesting → retest_done
      fail         retesting → wait_retest（次数已计，不回退）
      reset        retest_done → not_started，  次数清零
      ignore       任意状态 → ignored（保留次数）
      unignore     ignored → not_started，      次数清零（恢复初始状态）
    """
    # 深拷贝：普通 JSON 列不追踪同对象原地修改，必须整体替换为新对象才会标记脏并落库
    items = copy.deepcopy(plan.items or {})
    item = items.get(item_key)
    if item is None:
        raise HTTPException(404, f"测试项「{NONPEN_ITEMS.get(item_key, item_key)}」不存在")
    status = item.get("status") or "not_started"
    allowed = NONPEN_ITEM_ACTIONS.get(status, set())
    if action not in allowed:
        raise HTTPException(
            400,
            f"「{NONPEN_ITEM_STATUS.get(status, status)}」状态下不支持操作"
            f"「{NONPEN_ITEM_ACTION_NAMES.get(action, action)}」",
        )
    if action == "start":
        item["status"] = "testing"
        item["first_times"] = (item.get("first_times") or 0) + 1
    elif action == "done":
        item["status"] = "wait_retest"
    elif action == "direct_done":
        item["status"] = "retest_done"
    elif action == "start_retest":
        item["status"] = "retesting"
        item["retest_times"] = (item.get("retest_times") or 0) + 1
    elif action == "pass":
        item["status"] = "retest_done"
    elif action == "fail":
        item["status"] = "wait_retest"
    elif action == "reset":
        item["status"] = "not_started"
        item["first_times"] = 0
        item["retest_times"] = 0
    elif action == "ignore":
        item["status"] = "ignored"
    elif action == "unignore":
        # 确认需求：取消忽略恢复初始状态，次数清零
        item["status"] = "not_started"
        item["first_times"] = 0
        item["retest_times"] = 0
    plan.items = items
    return item


def compute_plan_stats(plans: list[NonpenPlan]) -> dict:
    """统计口径（对应需求 2.8 五张卡片）：

    - total：漏扫基线工单总数；
    - retest_done：复测完成数——存在至少一个非忽略测试项，且全部非忽略项均为 retest_done；
      全部测试项被忽略的计划不计入复测完成；
    - baseline_times / host_times / web_times：三类测试的「测试次数」——初测与复测针对
      同一测试项，合计按一次计（按初测次数统计，复测不重复计数）。
    """
    total = retest_done = baseline_times = host_times = web_times = 0
    for p in plans:
        items = p.items or {}
        total += 1
        active = [s for s in items.values() if s.get("status") != "ignored"]
        if active and all(s.get("status") == "retest_done" for s in active):
            retest_done += 1
        baseline_times += (items.get("baseline") or {}).get("first_times") or 0
        host_times += (items.get("host") or {}).get("first_times") or 0
        web_times += (items.get("web") or {}).get("first_times") or 0
    return {
        "total": total,
        "retest_done": retest_done,
        "baseline_times": baseline_times,
        "host_times": host_times,
        "web_times": web_times,
    }


def sync_linked_fields(source, target) -> None:
    """联动双向同步：把 source 的公共字段复制到 target（无权限校验，由调用方保证）。

    编辑测试计划 → 同步联动漏扫基线工单；编辑联动漏扫基线工单 → 同步来源测试计划。
    """
    for f in SYNC_FIELDS:
        val = getattr(source, f)
        setattr(target, f, list(val) if isinstance(val, list) else val)
