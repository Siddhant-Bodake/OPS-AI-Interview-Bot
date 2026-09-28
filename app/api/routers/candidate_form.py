"""FastAPI wrapper for candidate application form submissions."""
from __future__ import annotations

import asyncpg
from asyncpg.exceptions import IntegrityConstraintViolationError
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.core.config import settings
from app.core.database import get_pool
from app.core.security import require_api_key
from app.modules.candidate_form import (
    CandidateFormCreate,
    CandidateFormService,
    CandidateFormSubmitResponse,
    CandidateNotFoundError,
    JobRoleNotFoundError,
    JobRoleOption,
    build_candidate_form_service,
)


router = APIRouter(
    prefix="/candidate-form",
    tags=["candidate-form"],
    dependencies=[Depends(require_api_key(settings.CANDIDATE_FORM_API_KEY, "candidate-form"))],
)


def get_service(pool: asyncpg.Pool = Depends(get_pool)) -> CandidateFormService:
    return build_candidate_form_service(pool)


@router.get("/roles", response_model=list[JobRoleOption])
async def list_active_roles(
    service: CandidateFormService = Depends(get_service),
) -> list[JobRoleOption]:
    return await service.list_active_roles()


@router.post("/submit", status_code=status.HTTP_201_CREATED)
async def submit_candidate_form(
    payload: CandidateFormCreate,
    background_tasks: BackgroundTasks,
    service: CandidateFormService = Depends(get_service),
) -> CandidateFormSubmitResponse:
    try:
        return await service.submit(payload, background_tasks)
    except CandidateNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No candidate found for this email",
        )
    except JobRoleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown or inactive applied_role_id: {exc.role_id}",
        )
    except IntegrityConstraintViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {exc}",
        )
    except asyncpg.PostgresError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {exc}",
        )
