"""Prototype write-path safeguards: process-local rate limiting for consequential simulation endpoints.

This is a lightweight in-process sliding-window limiter (no Redis, no paid infrastructure). It protects the
two POST simulation endpoints only; read-only GET dashboard traffic is never limited. It is **not** an
enterprise WAF or distributed rate limiter: limits are per API process, reset on restart, and behind a
shared proxy several users can share one client key.

Configuration (numbers only):
* ``AGENTFLOW_RATE_LIMIT_SIMULATIONS`` — simulation requests allowed per client per window (default 20; 0 disables)
* ``AGENTFLOW_RATE_LIMIT_WINDOW_SECONDS`` — window length in seconds (default 60)
* ``AGENTFLOW_RATE_LIMIT_TRUST_FORWARDED_FOR`` — "1" to key clients by the first X-Forwarded-For address
  (only behind a trusted proxy; the header is client-controlled otherwise). Default: the socket peer address.
"""
from __future__ import annotations

import math
import os
import threading
import time
from collections import deque
from dataclasses import dataclass

LABEL = "Prototype process-local rate limiting — not enterprise WAF protection."


@dataclass(frozen=True)
class RateLimitConfig:
    max_requests: int = 20
    window_seconds: float = 60.0
    trust_forwarded_for: bool = False

    def __post_init__(self) -> None:
        if self.max_requests < 0:
            raise ValueError("AGENTFLOW_RATE_LIMIT_SIMULATIONS must be >= 0")
        if not (self.window_seconds > 0 and math.isfinite(self.window_seconds)):
            raise ValueError("AGENTFLOW_RATE_LIMIT_WINDOW_SECONDS must be > 0")

    @property
    def enabled(self) -> bool:
        return self.max_requests > 0


def config_from_env(env: dict | None = None) -> RateLimitConfig:
    env = os.environ if env is None else env

    def num(name: str, default, cast):
        raw = str(env.get(name, "")).strip()
        if not raw:
            return default
        try:
            return cast(raw)
        except ValueError as exc:
            raise ValueError(f"{name} must be a number") from exc

    return RateLimitConfig(max_requests=num("AGENTFLOW_RATE_LIMIT_SIMULATIONS", 20, int),
                           window_seconds=num("AGENTFLOW_RATE_LIMIT_WINDOW_SECONDS", 60.0, float),
                           trust_forwarded_for=str(env.get("AGENTFLOW_RATE_LIMIT_TRUST_FORWARDED_FOR", "")).strip() == "1")


class RateLimiter:
    def __init__(self, cfg: RateLimitConfig | None = None, clock=time.monotonic):
        self.cfg = cfg or config_from_env()
        self._clock = clock
        self._hits: dict[tuple[str, str], deque] = {}
        self._lock = threading.Lock()

    def client_key(self, peer: str | None, forwarded_for: str | None) -> str:
        if self.cfg.trust_forwarded_for and forwarded_for:
            return forwarded_for.split(",")[0].strip()[:64] or "unknown"
        return (peer or "unknown")[:64]

    def check(self, scope: str, client: str) -> tuple[bool, int]:
        """Record one request. Returns (allowed, retry_after_seconds)."""
        if not self.cfg.enabled:
            return True, 0
        now = self._clock()
        key = (scope, client)
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] >= self.cfg.window_seconds:
                q.popleft()
            if len(q) >= self.cfg.max_requests:
                return False, max(1, math.ceil(self.cfg.window_seconds - (now - q[0])))
            q.append(now)
            if len(self._hits) > 10_000:  # bound memory: drop idle clients
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def describe(self) -> dict:
        return {"label": LABEL, "enabled": self.cfg.enabled, "max_requests": self.cfg.max_requests,
                "window_seconds": self.cfg.window_seconds, "scope": "POST simulation endpoints only",
                "keyed_by": "X-Forwarded-For (trusted proxy)" if self.cfg.trust_forwarded_for else "client address"}


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter
