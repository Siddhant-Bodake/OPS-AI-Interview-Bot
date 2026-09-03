from __future__ import annotations

import logging
from uuid import UUID

import asyncpg

from app.modules.candidate_form.schemas import (
    CandidateFormCreate,
    CandidateFormSubmitResponse,
    JobRoleOption,
)
from app.modules.candidate_form.store import CandidateFormStore

logger = logging.getLogger(__name__)


class CandidateNotFoundError(Exception):
    def __init__(self, email: str):
        self.email = email
        super().__init__(f"No candidate found for this email: {email}")


class JobRoleNotFoundError(Exception):
    def __init__(self, role_id: UUID):
        self.role_id = role_id
        super().__init__(f"No active job role found for id={role_id}")


class CandidateFormService:
    def __init__(self, store: CandidateFormStore):
        self._store = store

    async def list_active_roles(self) -> list[JobRoleOption]:
        return await self._store.list_active_job_roles()

    async def submit(self, data: CandidateFormCreate) -> CandidateFormSubmitResponse:
        role = await self._store.get_active_job_role(data.applied_role_id)
        if role is None:
            raise JobRoleNotFoundError(data.applied_role_id)

        candidate = await self._store.find_candidate_by_email(str(data.email_address))
        if candidate is None:
            raise CandidateNotFoundError(str(data.email_address))

        if candidate.candidate_name.strip().lower() != data.full_name.strip().lower():
            logger.warning(
                "Submitted full_name %r differs from candidate_name %r for email %s",
                data.full_name,
                candidate.candidate_name,
                data.email_address,
            )

        record = await self._store.insert(
            candidate_id=candidate.candidate_id,
            data=data,
        )
        await self._store.mark_form_submitted(candidate.candidate_id)
        return CandidateFormSubmitResponse(
            id=record.id,
            candidate_id=record.candidate_id,
            applied_role_id=record.applied_role_id,
            message="Application submitted successfully",
            created_at=record.created_at,
        )


def build_candidate_form_service(pool: asyncpg.Pool) -> CandidateFormService:
    return CandidateFormService(CandidateFormStore(pool))
