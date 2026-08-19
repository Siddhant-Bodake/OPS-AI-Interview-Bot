"""
LLM-based resume extraction (Module 2). Reuses the same throttle+retry
pattern as Module 8's engine for Gemini free-tier RPM limits.
"""
from __future__ import annotations

import asyncio
import time

from google import genai
from google.genai import errors, types

from . import config, prompts
from .schemas import ResumeProfile, RoleRequirements, SkillMatchResponse, ProjectRelevanceResponse, SkillMatch


class ResumeExtractor:
    def __init__(self, gemini_client: genai.Client):
        self.client = gemini_client
        self._rate_lock = asyncio.Lock()
        self._last_call_at: float = 0.0

    async def _generate(self, prompt: str, schema: type, _retries: int = 3):
        async with self._rate_lock:
            wait = config.MIN_SECONDS_BETWEEN_GEMINI_CALLS - (time.time() - self._last_call_at)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call_at = time.time()

        for attempt in range(_retries):
            try:
                response = await self.client.aio.models.generate_content(
                    model=config.GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=schema,
                    ),
                )
                return response.parsed
            except errors.APIError as e:
                if e.code == 429 and attempt < _retries - 1:
                    await asyncio.sleep(config.MIN_SECONDS_BETWEEN_GEMINI_CALLS * (2 ** attempt))
                    continue
                raise

    async def extract(self, resume_text: str, role: str, jd_text: str) -> ResumeProfile:
        prompt = prompts.EXTRACTION_PROMPT.format(role=role, jd_text=jd_text, resume_text=resume_text)
        result = await self._generate(prompt, ResumeProfile)
        if result is None:
            # Fallback: return empty profile if LLM fails
            return ResumeProfile()
        return result

    
    async def score_projects(self, profile: ResumeProfile, role_requirements: RoleRequirements) -> ProjectRelevanceResponse:
        if not profile.projects:
            return ProjectRelevanceResponse(projects_score=0.0)  # skip the call, save quota — no projects, no ambiguity

        projects_block = "\n".join(
            f"- {p.name}: {p.description or '(no description)'} "
            f"[{', '.join(p.technologies) if p.technologies else 'no tech listed'}]"
            for p in profile.projects
        )
        prompt = prompts.PROJECT_RELEVANCE_PROMPT.format(
            role=role_requirements.role,
            jd_text=", ".join(role_requirements.jd_keywords),
            projects_block=projects_block,
        )
        result = await self._generate(prompt, ProjectRelevanceResponse)
        if result is None:
            # Fallback: return zero score if LLM fails
            return ProjectRelevanceResponse(projects_score=0.0)
        return result

    
    async def match_skills(self, profile: ResumeProfile, role_requirements: RoleRequirements) -> SkillMatchResponse:
        skills_block = "\n".join(f"- {s.name}: {s.years_experience}y" for s in profile.skills) or "(none listed)"
        certifications_block = "\n".join(f"- {c.name}" + (f" ({c.issuer})" if c.issuer else "") for c in profile.certifications) or "(none listed)"
        prompt = prompts.SKILL_MATCH_PROMPT.format(
            role=role_requirements.role,
            jd_keywords=", ".join(role_requirements.jd_keywords),
            candidate_skills_block=skills_block,
            candidate_certifications_block=certifications_block,
        )
        result = await self._generate(prompt, SkillMatchResponse)
        if result is None:
            # Fallback: create empty matches if LLM fails
            from .schemas import SkillMatch
            return SkillMatchResponse(matches=[
                SkillMatch(jd_keyword=kw, matched=False, matched_via="none", estimated_years=0.0)
                for kw in role_requirements.jd_keywords
            ])
        return result