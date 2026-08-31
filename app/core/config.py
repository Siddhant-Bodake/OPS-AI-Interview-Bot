"""
Shared app-level settings, env-driven. Secrets and infra endpoints live
here so every module reads from one place instead of scattering os.getenv
calls around the codebase.
"""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    ROLE_CONFIG_PATH: str = os.getenv("ROLE_CONFIG_PATH", "config/roles_config.json")
    RESUME_SCORING_API_KEY: str = os.getenv("RESUME_SCORING_API_KEY", "")  # shared secret, n8n sends this back

    # URL-based resume download settings
    ALLOWED_RESUME_DOMAINS: str = os.getenv("ALLOWED_RESUME_DOMAINS", "amazonaws.com,drive.google.com")
    RESUME_DOWNLOAD_TIMEOUT: int = int(os.getenv("RESUME_DOWNLOAD_TIMEOUT", "30"))
    RESUME_MAX_URL_FILE_SIZE: int = int(os.getenv("RESUME_MAX_URL_FILE_SIZE", str(10 * 1024 * 1024)))  # 10 MB

settings = Settings()