"""共用工具：retry decorator"""
from __future__ import annotations

import functools
import logging
import time
from typing import Callable

logger = logging.getLogger(__name__)


def retry(times: int = 3, delay: float = 2.0, backoff: float = 2.0):
    """重試 decorator。失敗時等 delay 秒後重試，每次延遲乘以 backoff。"""
    def deco(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            wait = delay
            last_err = None
            for attempt in range(1, times + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    last_err = e
                    if attempt < times:
                        logger.warning("%s 失敗 (第 %d/%d 次): %s — %.1fs 後重試",
                                       fn.__name__, attempt, times, e, wait)
                        time.sleep(wait)
                        wait *= backoff
                    else:
                        logger.error("%s 重試 %d 次後仍失敗: %s", fn.__name__, times, e)
            raise last_err
        return wrapper
    return deco
