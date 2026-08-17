"""
Redis-backed persistence for InterviewState (Module 8).

Write-through per answer: save() is called immediately after every scored
answer, not just at the end of the interview. This is what lets a dropped
call/tab resume from where it left off (Module 6 / Module 7 reconnect logic),
and lets a hard failure still preserve partial, usable data.
"""

from __future__ import annotations

import redis.asyncio as redis

from .state import InterviewState

SESSION_KEY_PREFIX = "interview:session:"
SESSION_TTL_SECONDS = 60 * 60 * 6  # 6h — comfortably covers retry/abandon windows


class InterviewStateStore:
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._redis = redis.from_url(redis_url, decode_responses=True)

    @staticmethod
    def _key(session_id: str) -> str:
        return f"{SESSION_KEY_PREFIX}{session_id}"

    async def save(self, state: InterviewState) -> None:
        """Write-through: called after every scored answer, not just at the end."""
        await self._redis.set(
            self._key(state.session_id),
            state.model_dump_json(),
            ex=SESSION_TTL_SECONDS,
        )

    async def load(self, session_id: str) -> InterviewState | None:
        raw = await self._redis.get(self._key(session_id))
        if raw is None:
            return None
        return InterviewState.model_validate_json(raw)

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(self._key(session_id))

    async def close(self) -> None:
        await self._redis.aclose()