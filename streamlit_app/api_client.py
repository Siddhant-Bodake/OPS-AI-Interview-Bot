from __future__ import annotations

import httpx

from streamlit_app.config import CANDIDATE_FORM_API_KEY, FASTAPI_BASE_URL

SUBMIT_URL = f"{FASTAPI_BASE_URL.rstrip('/')}/candidate-form/submit"


class CandidateFormApiError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def submit_application(payload: dict) -> dict:
    if not CANDIDATE_FORM_API_KEY:
        raise CandidateFormApiError(500, "CANDIDATE_FORM_API_KEY is not set.")
    try:
        response = httpx.post(
            SUBMIT_URL,
            json=payload,
            headers={"X-Api-Key": CANDIDATE_FORM_API_KEY},
            timeout=30.0,
        )
    except httpx.RequestError as exc:
        raise CandidateFormApiError(503, f"Could not reach the API: {exc}") from exc

    if response.status_code == 201:
        return response.json()

    detail = _extract_detail(response)
    raise CandidateFormApiError(response.status_code, detail)


def _extract_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text or f"Request failed with status {response.status_code}"
    detail = body.get("detail", body)
    if isinstance(detail, list):
        return "; ".join(str(item.get("msg", item)) for item in detail)
    return str(detail)
