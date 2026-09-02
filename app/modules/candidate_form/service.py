from __future__ import annotations

import logging

import asyncpg

from app.core.config import settings
from app.modules.candidate_form.schemas import (
    CandidateFormCreate,
    CandidateFormSubmitResponse,
)
from app.modules.candidate_form.store import CandidateFormStore
from app.modules.resume_scoring.role_config import RoleNotFoundError, get_role

logger = logging.getLogger(__name__)


class CandidateNotFoundError(Exception):
    def __init__(self, email: str):
        self.email = email
        super().__init__(f"No candidate found for this email: {email}")


class CandidateFormService:
    def __init__(self, store: CandidateFormStore):
        self._store = store

    async def submit(self, data: CandidateFormCreate) -> CandidateFormSubmitResponse:
        applied_role_display = self._resolve_applied_role_display(data)

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
            applied_role_display=applied_role_display,
            data=data,
        )
        return CandidateFormSubmitResponse(
            id=record.id,
            candidate_id=record.candidate_id,
            message="Application submitted successfully",
            created_at=record.created_at,
        )

    def _resolve_applied_role_display(self, data: CandidateFormCreate) -> str:
        if data.applied_role_other:
            return f"Other: {data.applied_role_other.strip()}"
        assert data.applied_role_id is not None
        try:
            role = get_role(data.applied_role_id, settings.ROLE_CONFIG_PATH)
        except RoleNotFoundError as exc:
            raise exc
        return role.role


def build_candidate_form_service(pool: asyncpg.Pool) -> CandidateFormService:
    return CandidateFormService(CandidateFormStore(pool))
