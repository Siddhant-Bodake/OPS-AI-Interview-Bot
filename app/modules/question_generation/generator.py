"""LLM-based question generation (Module 4). No DB access — pure generation
given already-fetched role config, bank questions, and resume profile."""
from __future__ import annotations

import asyncio
import time
from collections import Counter

from google import genai
from google.genai import errors, types

from . import config, prompts
from .schemas import GeneratedQuestion, QuestionGenerationResponse
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

    def _analyze_bank(self, bank_questions: list[dict]) -> dict:
        """Analyze bank questions by domain and type."""
        analysis = {
            "by_domain": {"technical": [], "behavioral": []},
            "by_type": {"core": [], "database": [], "scenario_based": [], "behavioral": []},
            "type_counts": {},
            "skill_matches": [],
        }
        for q in bank_questions:
            domain = q.get("domain", "")
            qtype = q.get("type", "")
            analysis["by_domain"].setdefault(domain, []).append(q)
            if qtype:
                analysis["by_type"].setdefault(qtype, []).append(q)
        analysis["type_counts"] = {t: len(qs) for t, qs in analysis["by_type"].items() if qs}
        return analysis

    def _build_type_distribution_hint(self, analysis: dict, technical_count: int) -> str:
        """Build the type distribution requirement hint."""
        ratio = config.TECHNICAL_TYPE_RATIO
        lines = ["TECHNICAL type distribution (must follow exactly):"]
        for t, r in ratio.items():
            count = max(1, round(technical_count * r))
            available = analysis["type_counts"].get(t, 0)
            lines.append(f"- {t}: {count} of {technical_count} technical questions ({int(r*100)}%)")
        lines.append(f"\nAvailable bank counts: {analysis['type_counts']}")
        return "\n".join(lines)

    def _build_skill_match_hint(self, analysis: dict, skills: list[str]) -> str:
        """Build skill-matched bank question hints."""
        if not skills:
            return ""
        relevant = []
        skill_set = {s.lower() for s in skills}
        for qtype, questions in analysis["by_type"].items():
            for q in questions:
                expected = [c.lower() for c in q.get("expected_concepts", [])]
                title = q.get("title", "").lower()
                if any(s in title or s in " ".join(expected) for s in skill_set):
                    relevant.append(q)
        if not relevant:
            return ""
        lines = ["RELEVANT bank questions to prioritize (match candidate skills):"]
        for q in relevant[:5]:
            lines.append(f"- [{q.get('type','')}] {q.get('title','')} — {q.get('question_text','')[:80]}")
        return "\n".join(lines)

    def _validate_output(self, questions: list[GeneratedQuestion],
                         total_count: int, technical_count: int,
                         behavioral_count: int, bank_count: int,
                         generated_count: int) -> list[GeneratedQuestion]:
        """Validate and fix LLM output."""
        # 1. Count validation
        if len(questions) != total_count:
            print(f"[question_generation] WARNING: expected {total_count} questions, got {len(questions)}")
            questions = questions[:total_count]

        # 2. Domain split validation
        tech = [q for q in questions if q.domain == "technical"]
        beh = [q for q in questions if q.domain == "behavioral"]
        if len(tech) != technical_count or len(beh) != behavioral_count:
            print(f"[question_generation] WARNING: domain split mismatch "
                  f"(expected {technical_count}T/{behavioral_count}B, "
                  f"got {len(tech)}T/{len(beh)}B)")
            # Trim or pad to match
            questions = tech[:technical_count] + beh[:behavioral_count]

        # 3. Type coverage validation (technical only)
        if config.ENFORCE_TYPE_COVERAGE:
            tech_qs = [q for q in questions if q.domain == "technical"]
            type_counts = Counter(q.type for q in tech_qs)
            required_types = {"core", "database", "scenario_based"}
            missing = required_types - set(type_counts.keys())
            if missing:
                print(f"[question_generation] WARNING: missing technical types: {missing}")

        # 4. Deduplication (simple text similarity)
        if config.DEDUPLICATION_ENABLED:
            seen = set()
            unique = []
            for q in questions:
                normalized = q.text.lower().strip()[:100]
                if normalized not in seen:
                    seen.add(normalized)
                    unique.append(q)
            if len(unique) != len(questions):
                print(f"[question_generation] WARNING: removed {len(questions) - len(unique)} duplicate(s)")
            questions = unique

        return questions

    async def generate(
        self,
        role: str,
        jd_text: str,
        seniority_tier: str,
        relevant_years: float,
        bank_questions: list[dict],
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

        # Pre-prompt analysis
        analysis = self._analyze_bank(bank_questions)

        # Build bank block
        bank_block = "\n".join(
            f"- [{q['domain']}] [{q.get('type','')}] [{q.get('difficulty','medium')}] {q['question_text']}"
            for q in bank_questions
        ) or "(none available)"

        # Build prompt injections
        type_hint = self._build_type_distribution_hint(analysis, technical_count)
        skill_hint = self._build_skill_match_hint(analysis, skills)

        prompt = prompts.GENERATION_PROMPT.format(
            role=role,
            seniority_tier=seniority_tier,
            relevant_years=relevant_years,
            jd_text=jd_text,
            bank_questions_block=bank_block,
            type_distribution_hint=type_hint,
            skill_match_hint=skill_hint,
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

        # Post-LLM validation
        result.questions = self._validate_output(
            result.questions, total_count, technical_count,
            behavioral_count, bank_count, generated_count
        )

        return result
