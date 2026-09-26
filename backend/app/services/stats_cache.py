"""统计结果短 TTL 缓存（P1-7）。

**为什么**：`build_stats`（看板 + 开放 API /open/stats）在 10 万级漏洞下要跑多次
全表聚合，页面反复切换筛选会重复计算。这里用进程内 TTL 缓存兜住重复计算，
并配套**显式失效**：漏洞 / 工单 / 报告 / 导入确认等写入路径调用 `invalidate()`，
保证数据变更后不出现长时间陈旧统计。

**为什么不做数据库预聚合**：单栈 PostgreSQL 下维护物化视图需要额外的刷新编排与回滚路径，
收益不如「短 TTL + 写入失效」直观；若后续数据量再上一个量级，按 `docs/ROADMAP.md` P2-4 重启评估。

缓存为进程内（每 API 进程一份），TTL 很短，不引入一致性风险；`cached_at` 随结果下发，
前端可展示统计生成时间。
"""
import copy
import threading
import time

# 缓存有效期（秒）：短 TTL 保证即使漏掉某个失效调用，陈旧窗口也有界
TTL_SECONDS = 30

_MAX_ENTRIES = 128
_lock = threading.Lock()
_store: dict[str, tuple[float, dict]] = {}


def cache_key(**params) -> str:
    """由筛选参数生成稳定缓存键（参数顺序无关）。"""
    parts = [f"{k}={params[k]!r}" for k in sorted(params) if params[k] not in (None, "")]
    return "|".join(parts) or "default"


def get(key: str) -> dict | None:
    """读取未过期缓存（返回深拷贝，避免调用方改写缓存内容）。"""
    with _lock:
        item = _store.get(key)
        if item is None:
            return None
        ts, value = item
        if time.time() - ts > TTL_SECONDS:
            _store.pop(key, None)
            return None
        return copy.deepcopy(value)


def put(key: str, value: dict) -> None:
    with _lock:
        if len(_store) >= _MAX_ENTRIES:
            # 容量兜底：清掉最旧的一批，避免无界增长（键数量受筛选组合限制）
            for old in sorted(_store, key=lambda k: _store[k][0])[: _MAX_ENTRIES // 4]:
                _store.pop(old, None)
        _store[key] = (time.time(), copy.deepcopy(value))


def invalidate() -> int:
    """失效全部统计缓存（数据写入路径调用）；返回清掉的条目数。"""
    with _lock:
        n = len(_store)
        _store.clear()
        return n
