"""로그인 시도 횟수 제한 (인메모리).

- 같은 키(IP, 아이디)에서 WINDOW_SECONDS 안에 MAX_ATTEMPTS번 실패하면
  LOCK_SECONDS 동안 로그인 시도를 막는다.
- 서버를 재시작하면 기록이 초기화되고, 워커 프로세스가 여러 개면 각각 따로 센다.
  (여러 인스턴스로 운영하게 되면 Redis 같은 공유 저장소로 교체)
"""
import time
from typing import Dict, List

from fastapi import HTTPException, status

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60
LOCK_SECONDS = 15 * 60

_failures: Dict[str, List[float]] = {}
_locked_until: Dict[str, float] = {}


def check_locked(*keys: str) -> None:
    """잠긴 키가 하나라도 있으면 429를 발생시킨다."""
    now = time.time()
    for key in keys:
        until = _locked_until.get(key)
        if until and until > now:
            wait = int(until - now) // 60 + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"로그인 시도가 너무 많습니다. {wait}분 후에 다시 시도해주세요.",
            )
        if until:
            _locked_until.pop(key, None)


def record_failure(*keys: str) -> None:
    now = time.time()
    for key in keys:
        recent = [t for t in _failures.get(key, []) if now - t < WINDOW_SECONDS]
        recent.append(now)
        _failures[key] = recent
        if len(recent) >= MAX_ATTEMPTS:
            _locked_until[key] = now + LOCK_SECONDS
            _failures.pop(key, None)


def reset(*keys: str) -> None:
    for key in keys:
        _failures.pop(key, None)
        _locked_until.pop(key, None)
