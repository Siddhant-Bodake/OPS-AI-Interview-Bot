from __future__ import annotations

import asyncio
import logging
from uuid import UUID

import asyncpg
import httpx
from fastapi import BackgroundTasks

from app.core.config import settings
from app.modules.candidate_form.schemas import (
    CandidateFormCreate,
    CandidateFormSubmitResponse,
    JobRoleOption,
)
from app.modules.candidate_form.store import CandidateFormStore

logger = logging.getLogger(__name__)


class CandidateNotFoundError(Exception):
    def __init__(self, email: str):
        self.email = email
        super().__init__(f"No candidate found for this email: {email}")


class JobRoleNotFoundError(Exception):
    def __init__(self, role_id: UUID):
        self.role_id = role_id
        super().__init__(f"No active job role found for id={role_id}")


async def _trigger_question_generation(candidate_id: UUID, pool: asyncpg.Pool) -> None:
    """Background task: wait 10s then generate questions for the candidate."""
    await asyncio.sleep(10)
    try:
        from app.modules.question_generation import QuestionGenerator, determine_seniority_tier
        from app.modules.question_generation.schemas import QuestionGenConfig
        from app.modules.interview_engine.engine import build_gemini_client

        store = CandidateFormStore(pool)
        result = await store.find_resume_score_id(candidate_id)
        if result is None:
            logger.warning("No resume_score found for candidate_id=%s — skipping question generation", candidate_id)
            return

        resume_score_id, role_id = result

        # Fetch role info from DB
        async with pool.acquire() as conn:
            role_row = await conn.fetchrow(
                "SELECT role_name, jd_text, seniority_tier, question_gen_config FROM job_roles WHERE id = $1",
                role_id,
            )
        if role_row is None:
            logger.warning("role_id=%s not found — skipping question generation", role_id)
            return

        import json
        seniority_bands = json.loads(role_row["seniority_tier"]) if isinstance(role_row["seniority_tier"], str) else role_row["seniority_tier"]
        q_config_dict = json.loads(role_row["question_gen_config"]) if role_row["question_gen_config"] else {}
        q_config = QuestionGenConfig(**q_config_dict) if q_config_dict else QuestionGenConfig()

        # Fetch candidate profile
        async with pool.acquire() as conn:
            profile_row = await conn.fetchrow(
                """SELECT relevant_years_experience, skills, work_experience, projects
                   FROM candidate_profiles WHERE resume_score_id = $1""",
                resume_score_id,
            )
        if profile_row is None:
            logger.warning("No candidate_profile for resume_score_id=%s — skipping", resume_score_id)
            return

        relevant_years = float(profile_row["relevant_years_experience"])
        seniority_tier = determine_seniority_tier(relevant_years, seniority_bands)

        # Fetch bank questions
        async with pool.acquire() as conn:
            bank_rows = await conn.fetch(
                """SELECT domain, question_text FROM question_bank_templates
                   WHERE role_id = $1 AND seniority_tier->>'tier' = $2 AND is_active = true""",
                role_id, seniority_tier,
            )

        bank_questions = []
        for r in bank_rows:
            domain = r["domain"]
            qt = r["question_text"]
            if isinstance(qt, dict):
                for category_key, category_data in qt.items():
                    if isinstance(category_data, dict) and "questions" in category_data:
                        for q in category_data["questions"]:
                            bank_questions.append({
                                "domain": domain,
                                "type": category_key if domain == "technical" else "",
                                "question_text": q.get("question", ""),
                                "title": q.get("title", ""),
                                "follow_up": q.get("follow_up", ""),
                                "difficulty": q.get("difficulty", "medium"),
                                "expected_concepts": q.get("expected_concepts", []),
                            })
            elif isinstance(qt, str):
                bank_questions.append({"domain": domain, "question_text": qt})

        skills = [s["name"] for s in json.loads(profile_row["skills"])]
        work_experience = [
            f"{w['role_title']} at {w['company']}" for w in json.loads(profile_row["work_experience"])
        ]
        projects = [p["name"] for p in json.loads(profile_row["projects"])]

        generator = QuestionGenerator(build_gemini_client())
        gen_result = await generator.generate(
            role_id=str(role_id),
            role=role_row["role_name"],
            jd_text=role_row["jd_text"],
            seniority_tier=seniority_tier,
            relevant_years=relevant_years,
            bank_questions=bank_questions,
            skills=skills,
            work_experience=work_experience,
            projects=projects,
            q_config=q_config,
        )

        # Group questions and assign IDs
        questions_json = [q.model_dump() for q in gen_result.questions]
        questions_grouped = {"technical": [], "behavioral": []}
        qt_counter = 1
        qbh_counter = 1
        for q in questions_json:
            if q["domain"] == "technical":
                q_id = f"qt_{qt_counter:03d}"
                qt_counter += 1
            else:
                q_id = f"qbh_{qbh_counter:03d}"
                qbh_counter += 1
            entry = {
                "id": q_id,
                "text": q["text"],
                "source": q["source"],
                "title": q.get("title", ""),
                "follow_up": q.get("follow_up", ""),
                "difficulty": q.get("difficulty", "medium"),
                "expected_concepts": q.get("expected_concepts", []),
            }
            if q["domain"] == "technical":
                entry["type"] = q.get("type", "")
            questions_grouped[q["domain"]].append(entry)

        # Store in DB
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO interview_question_sets
                   (candidate_id, role_id, resume_score_id, seniority_tier, question_count, questions)
                   VALUES ($1, $2, $3, $4::jsonb, $5, $6::jsonb)""",
                candidate_id, role_id, resume_score_id,
                json.dumps({"tier": seniority_tier}), len(questions_json), json.dumps(questions_grouped),
            )
            await conn.execute(
                "UPDATE candidates SET is_question_generated = TRUE WHERE id = $1",
                candidate_id,
            )
        logger.info("Stored %d questions in interview_question_sets for candidate_id=%s", len(questions_json), candidate_id)

        # # Dump to JSON
        # from pathlib import Path
        # dump_dir = Path(r"D:\OPS\OPS-AI-Interview-Bot\backend\docs\temp")
        # dump_dir.mkdir(parents=True, exist_ok=True)
        # dump_payload = {
        #     "candidate_id": str(candidate_id),
        #     "role_id": str(role_id),
        #     "resume_score_id": str(resume_score_id),
        #     "seniority_tier": seniority_tier,
        #     "relevant_years": relevant_years,
        #     "question_count": len(questions_json),
        #     "questions": questions_grouped,
        # }
        # file_name = f"question_gen_{str(candidate_id)[:8]}.json"
        # dump_path = dump_dir / file_name
        # dump_path.write_text(json.dumps(dump_payload, indent=2))
        # logger.info("Dumped question output to %s", dump_path)

    except Exception:
        logger.exception("Background question generation failed for candidate_id=%s", candidate_id)


class CandidateFormService:
    def __init__(self, store: CandidateFormStore):
        self._store = store

    async def list_active_roles(self) -> list[JobRoleOption]:
        return await self._store.list_active_job_roles()

    async def submit(
        self,
        data: CandidateFormCreate,
        background_tasks: BackgroundTasks,
    ) -> CandidateFormSubmitResponse:
        role = await self._store.get_active_job_role(data.applied_role_id)
        if role is None:
            raise JobRoleNotFoundError(data.applied_role_id)

        candidate = await self._store.find_candidate_by_email(str(data.email_address))
        if candidate is None:
            raise CandidateNotFoundError(str(data.email_address))

        if candidate.candidate_name.strip().lower() != data.full_name.strip().lower():
            logger.warning(
                "Submitted full_name %r differs from candidate_name %r for email %s",
                data.full_name,
                candidate.candidate_name,
                data.email_address,
            )

        record = await self._store.insert(
            candidate_id=candidate.candidate_id,
            data=data,
        )
        await self._store.mark_form_submitted(candidate.candidate_id)

        # Send webhook to n8n with candidate_id
        logger.info("[webhook] FIRST_TIME_SCHEDULE_WEBHOOK setting = %r", settings.FIRST_TIME_SCHEDULE_WEBHOOK)
        if settings.FIRST_TIME_SCHEDULE_WEBHOOK:
            try:
                logger.info("[webhook] Sending webhook to n8n for candidate_id=%s", candidate.candidate_id)
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        settings.FIRST_TIME_SCHEDULE_WEBHOOK,
                        json={"candidate_id": str(candidate.candidate_id)},
                        timeout=10.0
                    )
                    logger.info("[webhook] n8n responded with status=%d, body=%s", response.status_code, response.text[:500])
            except Exception as exc:
                logger.error("[webhook] Failed to send webhook to n8n: %s", exc, exc_info=True)
        else:
            logger.warning("[webhook] FIRST_TIME_SCHEDULE_WEBHOOK is not set — skipping webhook call")

        # Schedule question generation in background (10s delay)
        background_tasks.add_task(
            _trigger_question_generation,
            candidate.candidate_id,
            self._store._pool,
        )

        return CandidateFormSubmitResponse(
            id=record.id,
            candidate_id=record.candidate_id,
            applied_role_id=record.applied_role_id,
            message="Application submitted successfully",
            created_at=record.created_at,
        )


def build_candidate_form_service(pool: asyncpg.Pool) -> CandidateFormService:
    return CandidateFormService(CandidateFormStore(pool))
