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

import time
from contextlib import contextmanager

@contextmanager
def timed(label: str):
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    print(f"  ⏱ {label}: {elapsed:.2f}s")


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
    while state.current_question() is not None and guard < 6:
        q = state.current_question()
        answer = sample_answers.get(q.domain.value, "I'd approach that methodically, step by step.")
        with timed(f"handle_answer [{q.domain.value}]"):
            result = await engine.handle_answer(state, role="Backend Engineer", answer_transcript=answer)
        print(f"Q[{q.domain.value}]: {q.text}\n  -> action={result['action']}"
              + (f", followup={result['followup_text']!r}" if result["followup_text"] else ""))
        guard += 1

    with timed("close_out"):
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


async def scenario_interrupt_with_question():
    """Candidate interrupts Q1 with a question instead of answering it.
    Confirms: it's queued, NOT scored, and Q1 is still the current
    question afterward (delivery layer should re-ask it)."""
    print("\n=== SCENARIO: interrupt_with_question [no-LLM] ===")
    engine, store = make_engine()
    state = engine.new_session(
        candidate_id="cand_interrupt", mode="web",
        scheduled_duration_seconds=900, question_bank=sample_question_bank(),
    )
    state.started_at = __import__("time").time()
    state.questions[0].asked_at = state.started_at
    await store.save(state)

    q1_before = state.current_question().text
    result = await engine.handle_candidate_utterance(
        state, role="Backend Engineer",
        transcript="Wait, what does the tech stack for this role actually look like?",
    )
    print("Result:", result)
    assert result["action"] == "clarifying_question_noted"
    assert state.current_question().text == q1_before, "Q1 should NOT have advanced"
    assert state.questions[0].score is None, "Q1 should NOT have been scored"
    print("Confirmed: question queued, Q1 unscored and unadvanced.")

    # Now the candidate actually answers Q1 — normal path resumes.
    result2 = await engine.handle_candidate_utterance(
        state, role="Backend Engineer",
        transcript="Sorry — anyway, on the project I mentioned, I used Python and Redis.",
    )
    print("After real answer:", result2["action"])
    print("Pending candidate questions at this point:", len(state.pending_candidate_questions))

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


async def scenario_answer_quality_spectrum():
    """Same technical question, three answer qualities, in separate
    single-question sessions. No assertions — this is for YOU to eyeball:
    do the scores actually separate strong / weak / off-topic sensibly?
    [LLM] — 3 sessions x up to 2 calls each (score + followup decision)."""
    print("\n=== SCENARIO: answer_quality_spectrum [LLM] ===")
    question_bank = [
        {"id": "q1", "domain": "technical", "text": "How would you design a rate limiter for an API?"}
    ]
    answers = {
        "strong": (
            "I'd use a token bucket per API key, stored in Redis with an atomic "
            "Lua script to avoid race conditions, refilling at a fixed rate. "
            "For distributed nodes I'd centralize the bucket in Redis rather than "
            "per-instance memory, and return a 429 with a Retry-After header when exhausted."
        ),
        "weak": "Umm, maybe just count the requests and block if too many? Not totally sure.",
        "off_topic": "I really enjoy hiking on weekends and I have two dogs.",
    }

    results = {}
    for label, answer in answers.items():
        engine, store = make_engine()
        state = engine.new_session(
            candidate_id=f"cand_quality_{label}", mode="web",
            scheduled_duration_seconds=900, question_bank=question_bank,
        )
        with timed(f"start_interview [{label}]"):
            await engine.start_interview(state, role="Backend Engineer", duration_minutes=15)
        with timed(f"handle_answer [{label}]"):
            result = await engine.handle_answer(state, role="Backend Engineer", answer_transcript=answer)
        score = state.questions[0].score
        results[label] = score
        print(f"[{label}] relevance={score.relevance} clarity={score.clarity} "
              f"tech_depth={score.tech_depth} avg={score.average}  "
              f"(followup_offered={result['action'] == 'followup'})")

        await store.close()

    
async def scenario_reask_on_nonanswer():
    """Off-topic answer should trigger a re-ask of the SAME question,
    not a follow-up. [LLM] — 1 call (score only, no follow-up-decision call)."""
    print("\n=== SCENARIO: reask_on_nonanswer [LLM] ===")
    engine, store = make_engine()
    state = engine.new_session(
        candidate_id="cand_reask", mode="web",
        scheduled_duration_seconds=900,
        question_bank=[{"id": "q1", "domain": "technical",
                         "text": "How would you design a rate limiter for an API?"}],
    )
    await engine.start_interview(state, role="Backend Engineer", duration_minutes=15)

    result = await engine.handle_answer(
        state, role="Backend Engineer",
        answer_transcript="I like hiking on weekends and I have two dogs.",
    )
    print("Result:", result)
    assert result["action"] == "reask_same_question"
    assert state.current_index == 0, "Should still be on Q1, not advanced"
    print("Confirmed: re-asked same question, did not advance or treat as follow-up.")
    await store.close()

async def scenario_reask_cap_exhausted():
    """Candidate gives an off-topic answer 3 times in a row on the same
    question. Should re-ask twice (cap=2), then give up and advance on the
    3rd non-answer rather than looping forever. [LLM] — 3 calls."""
    print("\n=== SCENARIO: reask_cap_exhausted [LLM] ===")
    engine, store = make_engine()
    state = engine.new_session(
        candidate_id="cand_reask_cap", mode="web",
        scheduled_duration_seconds=900,
        question_bank=[{"id": "q1", "domain": "technical",
                         "text": "How would you design a rate limiter for an API?"}],
    )
    await engine.start_interview(state, role="Backend Engineer", duration_minutes=15)

    off_topic = "I really enjoy hiking on weekends."
    for attempt in range(1, 4):
        result = await engine.handle_answer(state, role="Backend Engineer", answer_transcript=off_topic)
        print(f"Attempt {attempt}: action={result['action']}, reask_count={state.questions[0].reask_count}")

    assert state.questions[0].reask_count == 2, "Should stop incrementing after cap"
    assert result["action"] == "interview_complete", "Should give up and advance past the last question"
    print("Confirmed: re-asked exactly 2 times, then gave up and moved on.")
    await store.close()


SCENARIOS = {
    "full_interview": scenario_full_interview,
    "anomaly_logging": scenario_anomaly_logging,
    "drop_and_resume": scenario_drop_and_resume,
    "failed_reconnect_usable": scenario_failed_reconnect_usable,
    "failed_reconnect_reschedule": scenario_failed_reconnect_reschedule,
    "interrupt_with_question": scenario_interrupt_with_question,
    "followup_cap": scenario_followup_cap,
    "answer_quality_spectrum": scenario_answer_quality_spectrum,
    "reask_on_nonanswer": scenario_reask_on_nonanswer,
    "reask_cap_exhausted": scenario_reask_cap_exhausted,
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