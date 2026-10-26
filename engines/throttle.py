"""Login throttling: exponential lockout after repeated failures (in-memory)."""
import threading
import time
from typing import Dict, Tuple

FREE_ATTEMPTS = 5          # failures allowed before locking
BASE_LOCK_S = 30           # first lock duration; doubles each further failure
MAX_LOCK_S = 15 * 60
RESET_AFTER_S = 30 * 60    # failure history forgotten after this long idle

_lock = threading.Lock()
_state: Dict[str, Tuple[int, float, float]] = {}  # key -> (failures, locked_until, last_failure)


def _keys(ip: str, username: str):
    return (f"ip:{ip}", f"user:{username.lower()}@{ip}")


def seconds_locked(ip: str, username: str) -> int:
    """Seconds the caller must wait, or 0 if allowed to try."""
    now = time.time()
    with _lock:
        waits = [max(0.0, _state[k][1] - now) for k in _keys(ip, username) if k in _state]
    return int(max(waits, default=0.0) + 0.999) if waits and max(waits) > 0 else 0


def record_failure(ip: str, username: str) -> None:
    now = time.time()
    with _lock:
        for k in _keys(ip, username):
            fails, _, last = _state.get(k, (0, 0.0, 0.0))
            if now - last > RESET_AFTER_S:
                fails = 0
            fails += 1
            lock = 0.0
            if fails >= FREE_ATTEMPTS:
                lock = min(MAX_LOCK_S, BASE_LOCK_S * 2 ** (fails - FREE_ATTEMPTS))
            _state[k] = (fails, now + lock, now)
        if len(_state) > 5000:  # bound memory
            for k in [k for k, v in _state.items() if now - v[2] > RESET_AFTER_S]:
                del _state[k]


def record_success(ip: str, username: str) -> None:
    with _lock:
        for k in _keys(ip, username):
            _state.pop(k, None)
