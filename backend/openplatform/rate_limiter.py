"""API Key 限流（进程内固定窗口）。

按 Key 统计每分钟请求数，超限返回 429 与 ``Retry-After``。
v1 为单进程内存实现：多实例部署需要换成 Redis 等共享存储，
否则每个实例各自计数（总量等于实例数 × 配额）。
"""

import os
import threading
import time
from typing import Dict, Tuple

DEFAULT_LIMIT_PER_MIN = int(os.getenv("OPEN_API_RATE_LIMIT_PER_MIN", "120"))


class RateLimiter:
    def __init__(self, limit: int = DEFAULT_LIMIT_PER_MIN, window_sec: float = 60.0):
        self.limit = max(1, int(limit))
        self.window = float(window_sec)
        self._counters: Dict[str, Tuple[float, int]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, now: float = None) -> Tuple[bool, int, float]:
        """记一次请求。

        返回 ``(是否放行, 剩余额度, 建议重试秒数)``。
        """
        current = time.monotonic() if now is None else now

        with self._lock:
            started, count = self._counters.get(key, (current, 0))
            if current - started >= self.window:
                started, count = current, 0

            count += 1
            self._counters[key] = (started, count)

            if count > self.limit:
                retry_after = max(0.0, self.window - (current - started))
                return False, 0, retry_after
            return True, self.limit - count, 0.0

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()


limiter = RateLimiter()
