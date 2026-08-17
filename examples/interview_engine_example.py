"""
Scenario runner for the Module 8 interview engine.

Run everything:      python -m examples.interview_engine_example
Run one scenario:     python -m examples.interview_engine_example --only full_interview

Scenarios that call Gemini are marked [LLM]; scenarios that only exercise
state/Redis logic are marked [no-LLM] and run instantly regardless of RPM.
"""
import argparse
import asyncio

from app.core.config import settings
from app.modules.interview_engine import InterviewEngine, InterviewStateStore
from app.modules.interview_engine.engine import build_gemini_client
from app.modules.interview_engine.state import AnomalyType, InterviewStatus


def make_engine() -> tuple[InterviewEngine, InterviewStateStore]:
    store = InterviewStateStore(redis_url=settings.REDIS_URL)
    engine = InterviewEngine(store=store, gemini_client=build_gemini_client())
    return engine, store


def sample_question_bank():
    return [
        {"id": "q1", "domain": "technical", "text": "Walk me through a recent project you're proud of."},
        {"id": "q2", "domain": "behavioral", "text": "Tell me about a time you disagreed with a teammate."},
    ]


# --------------------------------------------------------------------- [LLM]

async def scenario_full_interview():
    """Answers both questions (handling any follow-ups the LLM decides to
    ask), queues a mid-interview candidate question, then closes out —
    exercising every LLM-driven branch: greeting, scoring, follow-up
    decision, and deferred Q&A."""
    print("\n=== SCENARIO: full_interview [LLM] ===")
    engine, store = make_engine()
    state = engine.new_session(
        candidate_id="cand_full",
        mode="web",
        scheduled_duration_seconds=15 * 60,
        question_bank=sample_question_bank(),
    )

    greeting = await engine.start_interview(state, role="Backend Engineer", duration_minutes=15)
    print("AI:", greeting)

    # Candidate asks something mid-interview — queued, not answered live.
    await engine.queue_candidate_question(state, "What's the team's on-call rotation like?")

    sample_answers = {
        "technical": "I built a resume-scoring pipeline in Python using an LLM for extraction, "
                     "Redis for state, and a weighted scoring formula across skills/experience/education.",
        "behavioral": "On a past team, I disagreed with a teammate over a caching strategy. "
                      "We whiteboarded both approaches, tested one against real traffic, and picked "
                      "the data-backed option together.",
    }

    # Walk the question list until it's exhausted, answering follow-ups too.
    guard = 0
    while state.current_question() is not None and guard < 6:  # guard: safety cap
        q = state.current_question()
        answer = sample_answers.get(q.domain.value, "I'd approach that methodically, step by step.")
        result = await engine.handle_answer(state, role="Backend Engineer", answer_transcript=answer)
        print(f"Q[{q.domain.value}]: {q.text}\n  -> action={result['action']}"
              + (f", followup={result['followup_text']!r}" if result["followup_text"] else ""))
        guard += 1

    closing = await engine.close_out(
        state, role="Backend Engineer", jd_context="Backend Engineer, Python, distributed systems"
    )
    print("Closing (deferred Q&A):\n", closing or "(no deferred questions)")
    print("Final domain scores:", state.domain_scores())
    print("Status:", state.status.value)

    await store.close()


# ------------------------------------------------------------------ [no-LLM]

async def scenario_anomaly_logging():
    """Logs a noise + a long-pause anomaly mid-interview. No LLM calls —
    just verifies anomalies persist immediately (the gap we fixed)."""
    print("\n=== SCENARIO: anomaly_logging [no-LLM] ===")
    engine, store = make_engine()
    state = engine.new_session(
        candidate_id="cand_anomaly", mode="telephonic",
        scheduled_duration_seconds=900, question_bank=sample_question_bank(),
    )
    await engine.log_anomaly(state, AnomalyType.NOISE)
    await engine.log_anomaly(state, AnomalyType.LONG_PAUSE)

    reloaded = await store.load(state.session_id)
    print("Anomalies persisted:", [a.type.value for a in reloaded.anomalies])
    await store.close()


async def scenario_drop_and_resume():
    """Simulates a mid-interview drop, then a successful reconnect —
    confirms resume() picks up from saved state (Module 6/7 requirement)."""
    print("\n=== SCENARIO: drop_and_resume [no-LLM] ===")
    engine, store = make_engine()
    state = engine.new_session(
        candidate_id="cand_drop_resume", mode="telephonic",
        scheduled_duration_seconds=900, question_bank=sample_question_bank(),
    )
    state.started_at = __import__("time").time()
    state.questions[0].answer_transcript = "Partial answer before the drop."
    await store.save(state)

    await engine.handle_drop(state)
    print("Status after drop:", state.status.value)

    resumed = await engine.resume(state.session_id)
    print("Status after resume:", resumed.status.value)
    print("Q1 answer survived drop:", resumed.questions[0].answer_transcript)
    await store.close()


async def scenario_failed_reconnect_usable():
    """Drop with NO reconnect, but >=60% of scheduled time was covered —
    should resolve to COMPLETED_PARTIAL, not a full reschedule."""
    print("\n=== SCENARIO: failed_reconnect_usable [no-LLM] ===")
    engine, store = make_engine()
    state = engine.new_session(
        candidate_id="cand_partial_ok", mode="web",
        scheduled_duration_seconds=600, question_bank=sample_question_bank(),
    )
    import time
    state.started_at = time.time() - 400  # 400/600 = 66% covered
    await store.save(state)

    status = await engine.finalize_after_failed_reconnect(state)
    print(f"Time coverage: {state.time_coverage_ratio():.0%} -> status: {status.value}")
    assert status == InterviewStatus.COMPLETED_PARTIAL
    await store.close()


async def scenario_failed_reconnect_reschedule():
    """Drop with NO reconnect, and <60% of scheduled time covered —
    should resolve to RESCHEDULE_REQUIRED."""
    print("\n=== SCENARIO: failed_reconnect_reschedule [no-LLM] ===")
    engine, store = make_engine()
    state = engine.new_session(
        candidate_id="cand_partial_bad", mode="web",
        scheduled_duration_seconds=600, question_bank=sample_question_bank(),
    )
    import time
    state.started_at = time.time() - 120  # 120/600 = 20% covered
    await store.save(state)

    status = await engine.finalize_after_failed_reconnect(state)
    print(f"Time coverage: {state.time_coverage_ratio():.0%} -> status: {status.value}")
    assert status == InterviewStatus.RESCHEDULE_REQUIRED
    await store.close()


async def scenario_followup_cap():
    """Answers question 1 twice in a row (as if a follow-up was asked and
    answered) and confirms a SECOND follow-up is never offered — verifies
    the hard cap independent of what the LLM might otherwise want to do."""
    print("\n=== SCENARIO: followup_cap [LLM] ===")
    engine, store = make_engine()
    state = engine.new_session(
        candidate_id="cand_cap", mode="web",
        scheduled_duration_seconds=900, question_bank=sample_question_bank()[:1],  # just q1
    )
    await engine.start_interview(state, role="Backend Engineer", duration_minutes=15)

    vague_answer = "Yeah, it went fine, we did stuff and it worked out."  # designed to invite a follow-up
    r1 = await engine.handle_answer(state, role="Backend Engineer", answer_transcript=vague_answer)
    print("First answer result:", r1["action"], r1["followup_text"])

    if r1["action"] == "followup":
        r2 = await engine.handle_answer(state, role="Backend Engineer", answer_transcript="More detail here.")
        print("Follow-up answer result:", r2["action"])
        assert r2["action"] in ("next_question", "interview_complete")
        print("Confirmed: no second follow-up was offered (cap holds).")
    else:
        print("LLM didn't ask a follow-up this run (its call) — cap wasn't exercised, but nothing to fix.")

    await store.close()


SCENARIOS = {
    "full_interview": scenario_full_interview,
    "anomaly_logging": scenario_anomaly_logging,
    "drop_and_resume": scenario_drop_and_resume,
    "failed_reconnect_usable": scenario_failed_reconnect_usable,
    "failed_reconnect_reschedule": scenario_failed_reconnect_reschedule,
    "followup_cap": scenario_followup_cap,
}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=list(SCENARIOS.keys()), default=None,
                         help="Run a single scenario instead of all of them.")
    args = parser.parse_args()

    to_run = [args.only] if args.only else list(SCENARIOS.keys())
    for name in to_run:
        await SCENARIOS[name]()


if __name__ == "__main__":
    asyncio.run(main())