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


settings = Settings()