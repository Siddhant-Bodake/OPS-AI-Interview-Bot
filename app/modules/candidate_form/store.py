from __future__ import annotations

import json
from uuid import UUID

import asyncpg

from app.modules.candidate_form.config import CANDIDATE_FORMS_TABLE, CANDIDATE_TABLE, JOB_ROLES_TABLE
from app.modules.candidate_form.schemas import CandidateFormCreate, CandidateFormRecord, JobRoleOption


class CandidateLookupResult:
    def __init__(self, candidate_id: UUID, candidate_name: str):
        self.candidate_id = candidate_id
        self.candidate_name = candidate_name


class CandidateFormStore:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def find_candidate_by_email(self, email: str) -> CandidateLookupResult | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT id, candidate_name
                FROM {CANDIDATE_TABLE}
                WHERE LOWER(email_address) = LOWER($1)
                LIMIT 1
                """,
                email,
            )
        if row is None:
            return None
        return CandidateLookupResult(candidate_id=row["id"], candidate_name=row["candidate_name"])

    async def list_active_job_roles(self) -> list[JobRoleOption]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT id, role_name
                FROM {JOB_ROLES_TABLE}
                WHERE is_active = TRUE
                ORDER BY role_name
                """
            )
        return [JobRoleOption(id=row["id"], name=row["role_name"]) for row in rows]

    async def get_active_job_role(self, role_id: UUID) -> JobRoleOption | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT id, role_name
                FROM {JOB_ROLES_TABLE}
                WHERE id = $1 AND is_active = TRUE
                """,
                role_id,
            )
        if row is None:
            return None
        return JobRoleOption(id=row["id"], name=row["role_name"])

    async def insert(
        self,
        candidate_id: UUID,
        data: CandidateFormCreate,
    ) -> CandidateFormRecord:
        linkedin_url = str(data.linkedin_portfolio_url) if data.linkedin_portfolio_url else None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO {CANDIDATE_FORMS_TABLE} (
                    candidate_id,
                    email_address,
                    full_name,
                    phone_number,
                    current_location,
                    applied_role_id,
                    total_experience_years,
                    relevant_experience_years,
                    primary_skills,
                    certifications,
                    employment_status,
                    notice_period,
                    available_from,
                    preferred_work_mode,
                    willing_to_relocate,
                    current_ctc_lpa,
                    expected_ctc_lpa,
                    interest_reason,
                    linkedin_portfolio_url,
                    hear_about,
                    hear_about_other,
                    consent_given
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8,
                    $9::jsonb, $10::jsonb, $11, $12, $13, $14, $15, $16, $17,
                    $18, $19, $20, $21, $22
                )
                RETURNING *
                """,
                candidate_id,
                str(data.email_address),
                data.full_name,
                data.phone_number,
                data.current_location,
                data.applied_role_id,
                data.total_experience_years,
                data.relevant_experience_years,
                json.dumps(data.primary_skills),
                json.dumps(data.certifications),
                data.employment_status.value,
                data.notice_period,
                data.available_from,
                data.preferred_work_mode.value,
                data.willing_to_relocate,
                data.current_ctc_lpa,
                data.expected_ctc_lpa,
                data.interest_reason,
                linkedin_url,
                data.hear_about.value,
                data.hear_about_other,
                data.consent_given,
            )
        record = dict(row)
        record["primary_skills"] = _json_list(record.get("primary_skills"))
        record["certifications"] = _json_list(record.get("certifications"))
        return CandidateFormRecord.model_validate(record)

    async def mark_form_submitted(self, candidate_id: UUID) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"""
                UPDATE {CANDIDATE_TABLE}
                SET is_form_submitted = TRUE
                WHERE id = $1
                """,
                candidate_id,
            )


def _json_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        parsed = json.loads(value)
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    return []
