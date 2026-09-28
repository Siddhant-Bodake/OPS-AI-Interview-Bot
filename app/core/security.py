"""Shared API-key auth dependency, parameterized per module's own secret."""
from __future__ import annotations

import secrets

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

# Single scheme definition — shows the "Authorize" button + lock icons in Swagger
_api_key_header = APIKeyHeader(name="x-api-key", auto_error=True)


def require_api_key(expected_key: str, key_name: str = "this service"):
    """Returns a FastAPI dependency that checks X-API-Key against expected_key.
    Fails closed: an unset expected_key means the service isn't configured
    for production yet, so it refuses rather than accepting everything."""
    async def _verify(api_key: str = Security(_api_key_header)) -> None:
        if not expected_key:
            raise HTTPException(status_code=500, detail=f"Server misconfigured: no API key set for {key_name}.")
        if not secrets.compare_digest(api_key, expected_key):
            raise HTTPException(status_code=401, detail="Invalid or missing API key.")
    return _verify