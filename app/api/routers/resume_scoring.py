"""FastAPI wrapper around Module 2 (resume parsing & scoring) for n8n to call."""
from __future__ import annotations

import secrets
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
import uvicorn

from app.core.config import settings
from app.modules.resume_scoring.client import build_gemini_client
from app.modules.resume_scoring import (
    ResumeExtractor,
    UnsupportedResumeFormat,
    extract_text,
    score_resume,
)
from app.modules.resume_scoring.role_config import RoleNotFoundError, get_role
from app.modules.resume_scoring.url_download import (
    download_resume_from_url,
    DomainNotAllowedError,
    GoogleDriveAccessError,
    ResumeDownloadTimeoutError,
    ResumeTooLargeError,
    ResumeURLError,
)


def verify_api_key(x_api_key: str = Header(...)) -> None:
    if not settings.RESUME_SCORING_API_KEY:
        raise HTTPException(status_code=500, detail="Server misconfigured: RESUME_SCORING_API_KEY not set.")
    if not secrets.compare_digest(x_api_key, settings.RESUME_SCORING_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


router = APIRouter(prefix="/resume-scoring", tags=["resume-scoring"], dependencies=[Depends(verify_api_key)])

_extractor: ResumeExtractor | None = None


def get_extractor() -> ResumeExtractor:
    global _extractor
    if _extractor is None:
        _extractor = ResumeExtractor(build_gemini_client())
    return _extractor


@router.post("/score")
async def score_resume_endpoint(
    candidate_id: str = Form(...),
    role_id: str = Form(...),
    resume_file: Optional[UploadFile] = File(None),
    resume_url: Optional[str] = Form(None),
    extractor: ResumeExtractor = Depends(get_extractor),
):
    if resume_file is None and resume_url is None:
        raise HTTPException(
            status_code=422,
            detail="Either 'resume_file' or 'resume_url' must be provided.",
        )
    if resume_file is not None and resume_url is not None:
        raise HTTPException(
            status_code=422,
            detail="Provide either 'resume_file' or 'resume_url', not both.",
        )

    try:
        role_requirements = get_role(role_id, settings.ROLE_CONFIG_PATH)
    except RoleNotFoundError:
        raise HTTPException(status_code=404, detail=f"Unknown role_id: {role_id!r}")

    tmp_path = None
    try:
        if resume_file is not None:
            suffix = Path(resume_file.filename or "").suffix or ""
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(await resume_file.read())
                tmp_path = tmp.name
        else:
            try:
                tmp_path, _suffix = await download_resume_from_url(resume_url)
            except DomainNotAllowedError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except GoogleDriveAccessError as e:
                raise HTTPException(status_code=422, detail=str(e))
            except ResumeTooLargeError as e:
                raise HTTPException(status_code=413, detail=str(e))
            except ResumeDownloadTimeoutError as e:
                raise HTTPException(status_code=504, detail=str(e))
            except ResumeURLError as e:
                raise HTTPException(status_code=400, detail=str(e))

        try:
            resume_text = extract_text(tmp_path)
        except UnsupportedResumeFormat as e:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported resume format: {e.extension!r}. Only .pdf and .docx are supported.",
            )

        profile = await extractor.extract(resume_text, role_requirements)
        scoring = await extractor.score_against_role(profile, role_requirements)
        breakdown = score_resume(profile, role_requirements, scoring)

        return {
            "candidate_id": candidate_id,
            "role_id": role_id,
            "breakdown": breakdown.model_dump(),
            "profile": profile.model_dump(),
        }
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
