"""LLM-based question generation (Module 4). No DB access — pure generation
given already-fetched role config, bank questions, and resume profile."""
from __future__ import annotations

import asyncio
import time

from google import genai
from google.genai import errors, types

from . import config, prompts
from .schemas import QuestionGenerationResponse
from .seniority import question_count_for


class QuestionGenerator:
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
            except Exception as e:
                print(f"[question_generation] WARNING: LLM response failed validation: {e}")
                return None

    async def generate(
        self,
        role: str,
        jd_text: str,
        seniority_tier: str,
        relevant_years: float,
        bank_questions: list[dict],   # [{domain, question_text}, ...] from question_bank_templates
        skills: list[str],
        work_experience: list[str],
        projects: list[str],
    ) -> QuestionGenerationResponse:
        total_count = question_count_for(
            relevant_years, config.BASE_QUESTION_COUNT, config.YEARS_DIVISOR, config.MAX_QUESTION_COUNT
        )
        technical_count = round(total_count * config.TECHNICAL_SPLIT)
        behavioral_count = total_count - technical_count
        bank_count = round(total_count * config.BANK_QUESTION_RATIO)
        generated_count = total_count - bank_count

        bank_block = "\n".join(
            f"- [{q['domain']}] [{q.get('type','')}] [{q.get('difficulty','medium')}] {q['question_text']}"
            for q in bank_questions
        ) or "(none available)"

        prompt = prompts.GENERATION_PROMPT.format(
            role=role,
            seniority_tier=seniority_tier,
            relevant_years=relevant_years,
            jd_text=jd_text,
            bank_questions_block=bank_block,
            skills_block=", ".join(skills) or "(none listed)",
            experience_block="; ".join(work_experience) or "(none listed)",
            projects_block="; ".join(projects) or "(none listed)",
            total_count=total_count,
            technical_count=technical_count,
            behavioral_count=behavioral_count,
            bank_count=bank_count,
            generated_count=generated_count,
        )

        result = await self._generate(prompt, QuestionGenerationResponse)
        if result is None:
            print(f"[question_generation] WARNING: generation returned None for role {role!r} "
                  f"— falling back to raw bank questions only.")
            fallback = bank_questions[:total_count] if bank_questions else []
            return QuestionGenerationResponse(questions=[
                {"domain": q["domain"], "text": q["question_text"], "source": "bank"} for q in fallback
            ])
        return result