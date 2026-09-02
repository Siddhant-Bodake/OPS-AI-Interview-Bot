from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_ROOT / ".env")


FASTAPI_BASE_URL: str = os.getenv("FASTAPI_BASE_URL", "http://localhost:8000")
CANDIDATE_FORM_API_KEY: str = os.getenv("CANDIDATE_FORM_API_KEY", "")
ROLE_CONFIG_PATH: str = os.getenv(
    "ROLE_CONFIG_PATH",
    str(BACKEND_ROOT / "config" / "role_config.json"),
)
