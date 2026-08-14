"""
Illustrative only — shows how a call site (the LiveKit agent handling either
the telephonic or web session) would drive the engine turn by turn.
Not runnable as-is: needs a real GEMINI_API_KEY and a running Redis instance.
"""

import asyncio
import os

from google import genai

from interview_engine import InterviewEngine, InterviewStateStore
from interview_engine.state import AnomalyType

# Example question bank shape — this is what Module 4 hands off to Module 8.
QUESTION_BANK = [
    {"id": "q1", "domain": "behavioral", "text": "Tell me about a time you disagreed with a teammate."},
    {"id": "q2", "domain": "technical", "text": "Walk me through how you'd design a rate limiter."},
    {"id": "q3", "domain": "technical", "text": "What's a bug you're proud of tracking down?"},
]


async def main():
    store = InterviewStateStore(redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    engine = InterviewEngine(store=store, gemini_client=client)

    state = engine.new_session(
        candidate_id="cand_123",
        mode="web",
        scheduled_duration_seconds=15 * 60,
        question_bank=QUESTION_BANK,
    )

    greeting = await engine.start_interview(state, role="Backend Engineer", duration_minutes=15)
    print("AI:", greeting)

    # Simulated candidate answers, one per current question, driving the loop.
    fake_answers = [
        "Sure — on my last team we disagreed about a caching strategy...",
        "I'd probably use a token bucket, per-user, backed by Redis...",
    ]

    for answer in fake_answers:
        # An anomaly can be logged at any point without touching the flow above.
        await engine.log_anomaly(state, AnomalyType.LONG_PAUSE)

        result = await engine.handle_answer(state, role="Backend Engineer", answer_transcript=answer)
        print("engine ->", result)
        if result["action"] == "interview_complete":
            break

    engine.queue_candidate_question(state, "What's the team's on-call rotation like?")

    closing = await engine.close_out(
        state, role="Backend Engineer", jd_context="Backend Engineer, on-call rotation: 1 week/month."
    )
    print("Closing remarks:\n", closing)

    print("Domain scores:", state.domain_scores())
    print("Anomalies:", state.anomalies)

    await store.close()


if __name__ == "__main__":
    asyncio.run(main())