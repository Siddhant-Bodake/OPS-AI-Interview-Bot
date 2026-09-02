"""Shared asyncpg connection pool for PostgreSQL."""
from __future__ import annotations

import asyncpg

_pool: asyncpg.Pool | None = None


async def init_db_pool(dsn: str) -> None:
    global _pool
    if _pool is not None:
        return
    _pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)


async def close_db_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialized")
    return _pool
