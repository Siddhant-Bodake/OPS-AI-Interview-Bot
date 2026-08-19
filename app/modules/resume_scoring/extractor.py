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
from .schemas import ResumeProfile, RoleRequirements, SkillMatch, ScoringResponse


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

    
    async def score_against_role(self, profile: ResumeProfile, role_requirements: RoleRequirements) -> ScoringResponse:
        summary_block = profile.summary or "(none provided)"
        skills_block = "\n".join(f"- {s.name}: {s.years_experience}y" for s in profile.skills) or "(none listed)"
        certifications_block = "\n".join(
            f"- {c.name}" + (f" ({c.issuer})" if c.issuer else "") for c in profile.certifications
        ) or "(none listed)"
        projects_block = "\n".join(
            f"- {p.name}: {p.description or '(no description)'} "
            f"[{', '.join(p.technologies) if p.technologies else 'no tech listed'}]"
            for p in profile.projects
        ) or "(none listed)"
        experience_block = "\n".join(
            f"- {w.role_title} at {w.company} ({w.start_date or '?'} - {w.end_date or 'Present'}): "
            f"{w.description or '(no description)'}"
            for w in profile.work_experience
        ) or "(none listed)"
        other_sections_block = "\n".join(
            f"- {o.section_title}: {o.content}" for o in profile.other_sections
        ) or "(none)"

        prompt = prompts.SCORING_PROMPT.format(
            role=role_requirements.role,
            expected_years=role_requirements.expected_years_experience,
            jd_text=", ".join(role_requirements.core_keywords + role_requirements.supporting_keywords),
            core_keywords=", ".join(role_requirements.core_keywords),
            supporting_keywords=", ".join(role_requirements.supporting_keywords) or "(none)",
            summary_block=summary_block,
            skills_block=skills_block,
            certifications_block=certifications_block,
            projects_block=projects_block,
            experience_block=experience_block,
            other_sections_block=other_sections_block,
        )
        result = await self._generate(prompt, ScoringResponse)
        if result is None:
            all_kw = role_requirements.core_keywords + role_requirements.supporting_keywords
            print(f"[resume_scoring] WARNING: scoring call returned None for candidate "
                  f"against role {role_requirements.role!r} — falling back to empty scoring.")
            return ScoringResponse(
                summary_relevance_percent=0.0,
                skill_matches=[
                    SkillMatch(jd_keyword=kw, matched=False, matched_via="none", estimated_years=0.0)
                    for kw in all_kw
                ],
                project_relevance=[],
                experience_relevance_percent=0.0,
                other_bonus_score=0.0,
            )
        return result