"""Per-role scoring config, fetched from PostgreSQL job_roles table."""
from __future__ import annotations

import json
import uuid

import asyncpg

from .schemas import RoleRequirements


class RoleNotFoundError(Exception):
    def __init__(self, role_id: str):
        self.role_id = role_id
        super().__init__(f"No role config found for role_id={role_id!r}")


async def get_role(role_id: str, pool: asyncpg.Pool) -> RoleRequirements:
    row = await pool.fetchrow(
        """SELECT role_name, jd_text, core_keywords, supporting_keywords,
                  expected_years_experience, threshold
           FROM job_roles WHERE id = $1 AND is_active = true""",
        uuid.UUID(role_id),
    )
    if row is None:
        raise RoleNotFoundError(role_id)

    # asyncpg returns JSONB columns as strings — parse them
    core_keywords = json.loads(row["core_keywords"]) if isinstance(row["core_keywords"], str) else row["core_keywords"]
    supporting_keywords = json.loads(row["supporting_keywords"]) if isinstance(row["supporting_keywords"], str) else row["supporting_keywords"]
    expected_years = json.loads(row["expected_years_experience"]) if isinstance(row["expected_years_experience"], str) else row["expected_years_experience"]

    return RoleRequirements(
        role=row["role_name"],
        jd_text=row["jd_text"],
        core_keywords=core_keywords,
        supporting_keywords=supporting_keywords,
        expected_years_experience=expected_years,
        threshold=float(row["threshold"]),
    )


async def list_roles(pool: asyncpg.Pool) -> dict[str, str]:
    rows = await pool.fetch("SELECT id, role_name FROM job_roles WHERE is_active = true")
    return {str(row["id"]): row["role_name"] for row in rows}
