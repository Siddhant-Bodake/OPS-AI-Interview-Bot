"""Shared API-key auth dependency, parameterized per module's own secret."""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException


def require_api_key(expected_key: str, key_name: str = "this service"):
    """Returns a FastAPI dependency that checks X-API-Key against expected_key.
    Fails closed: an unset expected_key means the service isn't configured
    for production yet, so it refuses rather than accepting everything."""
    async def _verify(x_api_key: str = Header(...)) -> None:
        if not expected_key:
            raise HTTPException(status_code=500, detail=f"Server misconfigured: no API key set for {key_name}.")
        if not secrets.compare_digest(x_api_key, expected_key):
            raise HTTPException(status_code=401, detail="Invalid or missing API key.")
    return _verify