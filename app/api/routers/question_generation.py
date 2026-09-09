"""FastAPI wrapper around Module 4 (AI question generation) for n8n to call
right after form submission."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import get_pool
from app.core.security import require_api_key
from app.modules.interview_engine.engine import build_gemini_client
from app.modules.question_generation import QuestionGenerator, determine_seniority_tier
from app.modules.question_generation.schemas import QuestionGenConfig

router = APIRouter(
    prefix="/question-generation",
    tags=["question-generation"],
    dependencies=[Depends(require_api_key(settings.QUESTION_GENERATION_API_KEY, "question-generation"))],
)

_generator: QuestionGenerator | None = None


def get_generator() -> QuestionGenerator:
    global _generator
    if _generator is None:
        _generator = QuestionGenerator(build_gemini_client())
    return _generator


class GenerateRequest(BaseModel):
    candidate_id: str
    role_id: str
    resume_score_id: str


@router.post("/generate")
async def generate_questions(
    body: GenerateRequest,
    generator: QuestionGenerator = Depends(get_generator),
):
    pool = get_pool()

    role_row = await pool.fetchrow(
        "SELECT id, role_name, jd_text, seniority_tier, question_gen_config FROM job_roles WHERE id = $1",
        uuid.UUID(body.role_id),
    )
    if role_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown role_id: {body.role_id!r}")

    profile_row = await pool.fetchrow(
        """SELECT relevant_years_experience, skills, work_experience, projects
           FROM candidate_profiles WHERE resume_score_id = $1""",
        uuid.UUID(body.resume_score_id),
    )
    if profile_row is None:
        raise HTTPException(status_code=404, detail=f"No candidate profile found for resume_score_id: {body.resume_score_id!r}")

    relevant_years = float(profile_row["relevant_years_experience"])
    seniority_bands = json.loads(role_row["seniority_tier"])
    seniority_tier = determine_seniority_tier(relevant_years, seniority_bands)

    bank_rows = await pool.fetch(
        """SELECT domain, question_text FROM question_bank_templates
           WHERE role_id = $1 AND seniority_tier->>'tier' = $2 AND is_active = true""",
        uuid.UUID(body.role_id), seniority_tier,
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

    # Parse question_gen_config from DB (JSONB comes as string from asyncpg)
    q_config_dict = json.loads(role_row["question_gen_config"]) if role_row["question_gen_config"] else {}
    q_config = QuestionGenConfig(**q_config_dict) if q_config_dict else QuestionGenConfig()

    result = await generator.generate(
        role_id=body.role_id,
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

    questions_json = [q.model_dump() for q in result.questions]

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

    set_id = await pool.fetchval(
        """INSERT INTO interview_question_sets
           (candidate_id, role_id, resume_score_id, seniority_tier, question_count, questions)
           VALUES ($1, $2, $3, $4::jsonb, $5, $6::jsonb)
           RETURNING id""",
        uuid.UUID(body.candidate_id), uuid.UUID(body.role_id), uuid.UUID(body.resume_score_id),
        json.dumps({"tier": seniority_tier}), len(questions_json), json.dumps(questions_grouped),
    )

    await pool.execute(
        "UPDATE candidates SET is_question_generated = TRUE WHERE id = $1",
        uuid.UUID(body.candidate_id),
    )

    # dump_dir = Path(r"D:\OPS\OPS-AI-Interview-Bot\backend\docs\temp")
    # dump_dir.mkdir(parents=True, exist_ok=True)

    # dump_payload = {
    #     "candidate_id": body.candidate_id,
    #     "role_id": body.role_id,
    #     "resume_score_id": body.resume_score_id,
    #     "seniority_tier": seniority_tier,
    #     "relevant_years": relevant_years,
    #     "question_count": len(questions_json),
    #     "questions": questions_grouped,
    # }

    # # file_name = f"question_gen_{body.candidate_id[:8]}_{int(time.time())}.json"
    # file_name = f"question_gen_{body.candidate_id[:8]}.json"
    # dump_path = dump_dir / file_name
    # dump_path.write_text(json.dumps(dump_payload, indent=2))
    # print(f"[question_generation] Dumped output to {dump_path}")

    return {
        "candidate_id": body.candidate_id,
        "role_id": body.role_id,
        "seniority_tier": seniority_tier,
        "question_count": len(questions_json),
        "questions": questions_grouped,
    }