"""反爬纪律单点：sleep 间隔 + 指数退避重试 + 当日磁盘缓存（实现方案 §2）。

全摄取层（akshare_client / curl_cffi_client）的网络外呼都必须经过这里；
纪律优先于进度——宁可慢、宁可降级，不打密集请求。
"""
from __future__ import annotations

import json
import random
import time
from datetime import date

from ..config import DATA_DIR

CACHE_ROOT = DATA_DIR / "cache"
CALL_INTERVAL = 0.6   # 相邻外呼最小间隔（秒），全进程共享
_MAX_TRIES = 3
_last_call = 0.0


def throttle() -> None:
    """外呼前调用：保证与上一次外呼间隔 ≥ CALL_INTERVAL。"""
    global _last_call
    wait = CALL_INTERVAL - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def retry(fn, *, what: str, tries: int = _MAX_TRIES):
    """指数退避（1s/2s/4s + 抖动）重试；全部失败抛 RuntimeError 交 source_map 降级。"""
    last_err: Exception | None = None
    for i in range(tries):
        throttle()
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 网络层异常种类繁杂，统一退避
            last_err = e
            if i < tries - 1:
                time.sleep((2 ** i) + random.uniform(0, 0.5))
    raise RuntimeError(f"{what} 重试 {tries} 次失败: {last_err}") from last_err


def cached(kind: str, key: str, fetch_fn):
    """当日磁盘缓存：data/cache/YYYY-MM-DD/{kind}__{key}.json。

    当天成功过的响应直接复用，不再外呼（接口漂移排查时删当日目录即可强制重拉）。
    """
    day_dir = CACHE_ROOT / date.today().isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"{kind}__{key}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass  # 缓存损坏视为 miss
    data = fetch_fn()
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data
