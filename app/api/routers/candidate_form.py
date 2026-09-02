"""FastAPI wrapper for candidate application form submissions."""
from __future__ import annotations

import secrets

import asyncpg
from asyncpg.exceptions import IntegrityConstraintViolationError
from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.config import settings
from app.core.database import get_pool
from app.modules.candidate_form import (
    CandidateFormCreate,
    CandidateFormService,
    CandidateFormSubmitResponse,
    CandidateNotFoundError,
    build_candidate_form_service,
)
from app.modules.resume_scoring.role_config import RoleNotFoundError


def verify_api_key(x_api_key: str = Header(...)) -> None:
    if not settings.CANDIDATE_FORM_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfigured: CANDIDATE_FORM_API_KEY not set.",
        )
    if not secrets.compare_digest(x_api_key, settings.CANDIDATE_FORM_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )


router = APIRouter(
    prefix="/candidate-form",
    tags=["candidate-form"],
    dependencies=[Depends(verify_api_key)],
)


def get_service(pool: asyncpg.Pool = Depends(get_pool)) -> CandidateFormService:
    return build_candidate_form_service(pool)


@router.post("/submit", status_code=status.HTTP_201_CREATED)
async def submit_candidate_form(
    payload: CandidateFormCreate,
    service: CandidateFormService = Depends(get_service),
) -> CandidateFormSubmitResponse:
    try:
        return await service.submit(payload)
    except CandidateNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No candidate found for this email",
        )
    except RoleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown role_id: {exc.role_id!r}",
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
