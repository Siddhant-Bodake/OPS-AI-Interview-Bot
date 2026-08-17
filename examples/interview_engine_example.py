"""
Minimal end-to-end example of driving the Module 8 engine for one session.
Run from the `backend/` root: python -m examples.interview_engine_example
Requires REDIS_URL and GEMINI_API_KEY set in the environment (see .env).
"""
import asyncio

from app.core.config import settings
from app.modules.interview_engine import InterviewEngine, InterviewStateStore
from app.modules.interview_engine.engine import build_gemini_client


async def main():
    store = InterviewStateStore(redis_url=settings.REDIS_URL)
    client = build_gemini_client()
    engine = InterviewEngine(store=store, gemini_client=client)

    question_bank = [
        {"id": "q1", "domain": "technical", "text": "Walk me through a recent project you're proud of."},
        {"id": "q2", "domain": "behavioral", "text": "Tell me about a time you disagreed with a teammate."},
    ]
    state = engine.new_session(
        candidate_id="cand_123",
        mode="web",
        scheduled_duration_seconds=15 * 60,
        question_bank=question_bank,
    )

    greeting = await engine.start_interview(state, role="Backend Engineer", duration_minutes=15)
    print("AI:", greeting)

    result = await engine.handle_answer(state, role="Backend Engineer",
                                         answer_transcript="I built a resume-scoring pipeline...")
    print(result)

    await engine.close_out(state, role="Backend Engineer", jd_context="Backend Engineer, Python, APIs")
    print("Final domain scores:", state.domain_scores())

    await store.close()


if __name__ == "__main__":
    asyncio.run(main())