import json
from google import genai
from google.genai import types

from app.core.config import settings
from app.core.database import get_pool


PROMPT_TEMPLATE = """
You are an expert technical interviewer evaluating a candidate's performance based on the transcript of an AI-conducted phone interview.
Below you have provided the Job Description, the Questions Bank and the Transcript of the interview.

JOB DESCRIPTION:
{jd}

SENIORITY LEVEL: 
{seniority_level}

QUESTION BANK:
{qb}

TRANSCRIPT:
{transcript}

Please analyze the transcript and provide the following:
1. `summary`: A concise 5-6 sentence summary of the candidate's performance describing in and out of each domain and aspects of the candidate.
2. `overall_score`: A float score from 0.0 to 10.0 representing the candidate's overall technical competency, communication skills and overall knowledge accrding to the expected job seniority.
3. `score_by_domain`: A JSON object breaking down the score by specific "domains" mentioned in JD (e.g., "React": 8.0, "Node.js": 7.5, "Communication": 9.0).
4. `overall_question_count`: The total number of distinct primary questions the AI interviewer intended to ask.
5. `asked_question_count`: The total number of questions actually asked by the AI (including follow-ups and conversational queries).
6. `qb_question_attempt_count`: The number of primary "Question Bank" topics/questions the AI managed to cover.
7. `answerd_question_count`: The total number of questions answered by the candidate.
Respond strictly in JSON format matching the schema below.
"""


async def evaluate_transcript(session_id: str) -> None:
    pool = get_pool()
    
    # 1. Fetch transcript from DB and related session info
    async with pool.acquire() as conn:
        record = await conn.fetchrow(
            """
            SELECT e.transcript, s.job_role, s.candidate_id 
            FROM interview_evaluations e
            JOIN interview_sessions s ON e.invses_id = s.id
            WHERE e.invses_id = $1
            """,
            session_id
        )
        if not record or not record["transcript"]:
            print(f"[transcript_eval] No transcript found for session {session_id}")
            return
            
        transcript_data = record["transcript"]
        job_role = record["job_role"]
        candidate_id = record["candidate_id"]

        if isinstance(transcript_data, str):
            transcript_data = json.loads(transcript_data)
            
        # Fetch JD, Seniority Level, and Question Bank using candidate_id
        jd_text = ""
        seniority_level = ""
        qb_text = ""
        
        if candidate_id:
            combined_record = await conn.fetchrow(
                """
                SELECT i.questions, j.jd_text, j.seniority_tier
                FROM interview_question_sets i
                JOIN job_roles j ON i.role_id = j.id
                WHERE i.candidate_id = $1
                ORDER BY i.created_at DESC 
                LIMIT 1
                """,
                candidate_id
            )
            
            if combined_record:
                # JD Text
                jd_text = combined_record.get("jd_text") or ""
                
                # Seniority Tier
                seniority_tier = combined_record.get("seniority_tier") or ""
                if isinstance(seniority_tier, (dict, list)):
                    seniority_level = json.dumps(seniority_tier)
                else:
                    seniority_level = str(seniority_tier)
                    
                # Questions (Question Bank)
                questions = combined_record.get("questions")
                if isinstance(questions, (dict, list)):
                    qb_text = json.dumps(questions, indent=2)
                else:
                    qb_text = str(questions)
    # Format transcript for prompt
    transcript_str = ""
    for msg in transcript_data:
        speaker = msg.get("speaker", "unknown").upper()
        text = msg.get("text") or msg.get("content", "")
        transcript_str += f"{speaker}: {text}\n\n"
        
    # 2. Call Gemini
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    
    prompt = PROMPT_TEMPLATE.format(
        transcript=transcript_str, 
        jd=jd_text, 
        seniority_level=seniority_level, 
        qb=qb_text
    )
    
    schema = {
        "type": "OBJECT",
        "properties": {
            "summary": {"type": "STRING"},
            "overall_score": {"type": "NUMBER"},
            "score_by_domain": {
                "type": "OBJECT",
                "additionalProperties": {"type": "NUMBER"}
            },
            "overall_question_count": {"type": "INTEGER"},
            "asked_question_count": {"type": "INTEGER"},
            "qb_question_attempt_count": {"type": "INTEGER"},
            "answered_question_count": {"type": "INTEGER"}
        },
        "required": ["summary", "overall_score", "score_by_domain", "overall_question_count", "asked_question_count", "qb_question_attempt_count", "answered_question_count"]
    }

    try:
        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL if hasattr(settings, "GEMINI_MODEL") else "gemini-3.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        result = response.parsed if hasattr(response, "parsed") else json.loads(response.text)
        
        # Extract values
        summary = result.get("summary")
        overall_score = result.get("overall_score")
        score_by_domain = result.get("score_by_domain", {})
        o_q_c = result.get("overall_question_count", 0)
        a_q_c = result.get("asked_question_count", 0)
        qb_q_a_c = result.get("qb_question_attempt_count", 0)
        ans_q_c = result.get("answered_question_count", 0)
        
        # 3. Update DB
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE interview_evaluations 
                SET summary = $1, 
                    overall_score = $2, 
                    score_by_domain = $3,
                    overall_question_count = $4,
                    asked_question_count = $5,
                    qb_question_attempt_count = $6,
                    answerd_question_count = $7,
                    updated_at = NOW()
                WHERE invses_id = $8
                """,
                summary,
                float(overall_score) if overall_score is not None else None,
                json.dumps(score_by_domain),
                o_q_c,
                a_q_c,
                qb_q_a_c,
                ans_q_c,
                session_id
            )
        print(f"[transcript_eval] Successfully evaluated session {session_id}")
        
    except Exception as e:
        print(f"[transcript_eval] Error evaluating session {session_id}: {e}")
