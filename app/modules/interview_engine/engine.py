"""
Core AI interview engine (Module 8).

Turn-by-turn flow, driven by the LLM for judgment calls (scoring, follow-up
decisions, deferred Q&A) but wrapped in deterministic Python control flow —
the LLM is never asked to freelance the overall loop, only to make narrow,
structured decisions within it. State is written through to Redis after
every scored answer so a dropped session never loses more than the
in-flight turn.
"""

from __future__ import annotations

import asyncio
import time
import uuid

from google import genai
from google.genai import errors, types

from app.core.config import settings

from . import config, prompts
from .llm_schemas import (
    DeferredQAResponse,
    FollowupDecisionResponse,
    GreetingResponse,
    ScoreResponse,
)
from .state import (
    AnomalyEvent,
    AnomalyType,
    AnswerScore,
    InterviewState,
    InterviewStatus,
    PendingCandidateQuestion,
    QuestionRecord,
)
from .store import InterviewStateStore


def build_gemini_client() -> genai.Client:
    return genai.Client(api_key=settings.GEMINI_API_KEY)


class InterviewEngine:
    def __init__(self, store: InterviewStateStore, gemini_client: genai.Client):
        self.store = store
        self.client = gemini_client
        self._rate_lock = asyncio.Lock()
        self._last_call_at: float = 0.0


    # ---------------------------------------------------------------- setup

    def new_session(
        self,
        candidate_id: str,
        mode: str,
        scheduled_duration_seconds: int,
        question_bank: list[dict],
    ) -> InterviewState:
        questions = [
            QuestionRecord(id=q["id"], domain=q["domain"], text=q["text"])
            for q in question_bank
        ]
        return InterviewState(
            session_id=str(uuid.uuid4()),
            candidate_id=candidate_id,
            mode=mode,
            scheduled_duration_seconds=scheduled_duration_seconds,
            questions=questions,
        )

    async def _generate(self, prompt: str, schema: type, _retries: int = 3):
        """Throttled + retried Gemini call. Throttling keeps a single session
        under free-tier RPM limits; retry handles the rare burst that still
        gets a 429 (e.g. another session running concurrently)."""
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
                    backoff = config.MIN_SECONDS_BETWEEN_GEMINI_CALLS * (2 ** attempt)
                    await asyncio.sleep(backoff)
                    continue
                raise


    # -------------------------------------------------------------- opening

    async def start_interview(self, state: InterviewState, role: str, duration_minutes: int) -> str:
        persona = prompts.INTERVIEWER_PERSONA.format(role=role)
        prompt = prompts.GREETING_PROMPT.format(persona=persona, duration_minutes=duration_minutes)
        greeting: GreetingResponse = await self._generate(prompt, GreetingResponse)

        state.started_at = time.time()
        state.status = InterviewStatus.IN_PROGRESS
        if state.questions:
            state.questions[0].asked_at = time.time()
        await self.store.save(state)
        return greeting.greeting_text


    # ------------------------------------------------------------- anomalies

    async def log_anomaly(self, state: InterviewState, anomaly_type: AnomalyType) -> None:
        state.anomalies.append(AnomalyEvent(type=anomaly_type))
        await self.store.save(state)

    async def queue_candidate_question(self, state: InterviewState, question_text: str) -> None:
        state.pending_candidate_questions.append(PendingCandidateQuestion(text=question_text))
        await self.store.save(state)


    # --------------------------------------------------------- answer intake

    async def handle_answer(
        self, state: InterviewState, role: str, answer_transcript: str
    ) -> dict:
        question = state.current_question()
        if question is None:
            raise ValueError("No current question to answer — interview may already be complete.")

        persona = prompts.INTERVIEWER_PERSONA.format(role=role)

        score_prompt = prompts.SCORE_ANSWER_PROMPT.format(
            persona=persona,
            domain=question.domain.value,
            question_text=question.text,
            answer_transcript=answer_transcript,
            score_min=config.SCORE_MIN,
            score_max=config.SCORE_MAX,
        )
        raw_score: ScoreResponse = await self._generate(score_prompt, ScoreResponse)

        question.answer_transcript = answer_transcript
        question.answered_at = time.time()
        question.score = AnswerScore(
            relevance=raw_score.relevance,
            clarity=raw_score.clarity,
            tech_depth=raw_score.tech_depth,
        )

        next_action = "advance"
        followup_text = None
        if not question.followup_used:
            followup_prompt = prompts.DECIDE_FOLLOWUP_PROMPT.format(
                persona=persona,
                question_text=question.text,
                answer_transcript=answer_transcript,
                relevance=raw_score.relevance,
                clarity=raw_score.clarity,
                tech_depth=raw_score.tech_depth,
            )
            decision: FollowupDecisionResponse = await self._generate(
                followup_prompt, FollowupDecisionResponse
            )
            if decision.should_ask_followup and decision.followup_text:
                question.followup_used = True
                followup_q = QuestionRecord(
                    id=f"{question.id}-f1",
                    domain=question.domain,
                    text=decision.followup_text,
                    is_followup=True,
                    parent_id=question.id,
                    asked_at=time.time(),
                )
                state.questions.insert(state.current_index + 1, followup_q)
                next_action = "followup"
                followup_text = decision.followup_text

        if next_action == "advance":
            state.current_index += 1
            if state.current_index < len(state.questions):
                state.questions[state.current_index].asked_at = time.time()
                next_action = "next_question"
            else:
                next_action = "interview_complete"

        await self.store.save(state)

        return {
            "action": next_action,
            "followup_text": followup_text,
            "next_question": state.current_question().text if state.current_question() else None,
        }

    
    # --------------------------------------------------------- intake router

    _QUESTION_STARTERS = (
        "what", "why", "how", "when", "where", "who",
        "can you", "could you", "is there", "do you", "does the",
    )

    def _looks_like_a_question(self, transcript: str) -> bool:
        """Cheap heuristic, no LLM call — keeps this check free even on a
        tight RPM quota, since it fires on every single turn. Good enough
        for the common barge-in case ('wait, what does...'); can be upgraded
        to an LLM classification call later if the heuristic proves too
        blunt in practice."""
        stripped = transcript.strip().lower()
        if not stripped:
            return False
        return stripped.endswith("?") or stripped.startswith(self._QUESTION_STARTERS)

    async def handle_candidate_utterance(
        self, state: InterviewState, role: str, transcript: str
    ) -> dict:
        """Entry point the delivery layer (Module 6/7) should call for every
        finalized STT transcript, instead of calling handle_answer directly.

        If the candidate interrupted with a question of their own rather
        than answering, it's queued (not scored) and the current question
        is NOT advanced — the delivery layer should re-prompt it."""
        if self._looks_like_a_question(transcript):
            await self.queue_candidate_question(state, transcript)
            current = state.current_question()
            return {
                "action": "clarifying_question_noted",
                "acknowledgment": "Good question — I'll come back to that at the end.",
                "repeat_question": current.text if current else None,
            }
        return await self.handle_answer(state, role, transcript)
    

    # ------------------------------------------------------------- wrap-up

    async def close_out(self, state: InterviewState, role: str, jd_context: str) -> str:
        closing_remarks = ""
        if state.pending_candidate_questions:
            persona = prompts.INTERVIEWER_PERSONA.format(role=role)
            questions_block = "\n".join(
                f"- {q.text}" for q in state.pending_candidate_questions
            )
            prompt = prompts.DEFERRED_QA_PROMPT.format(
                persona=persona, jd_context=jd_context, questions_block=questions_block
            )
            result: DeferredQAResponse = await self._generate(prompt, DeferredQAResponse)
            for pair, pending in zip(result.answers, state.pending_candidate_questions):
                pending.answer_text = pair.answer
                pending.answered_at = time.time()
            closing_remarks = "\n".join(f"Q: {p.question}\nA: {p.answer}" for p in result.answers)

        state.ended_at = time.time()
        state.status = InterviewStatus.COMPLETED
        await self.store.save(state)
        return closing_remarks


    # ------------------------------------------------------- drop / resume

    async def handle_drop(self, state: InterviewState) -> InterviewStatus:
        state.status = InterviewStatus.DROPPED
        await self.store.save(state)
        return state.status

    async def resume(self, session_id: str) -> InterviewState | None:
        state = await self.store.load(session_id)
        if state is None:
            return None
        state.status = InterviewStatus.IN_PROGRESS
        await self.store.save(state)
        return state

    async def finalize_after_failed_reconnect(self, state: InterviewState) -> InterviewStatus:
        if state.is_usable_if_dropped():
            state.status = InterviewStatus.COMPLETED_PARTIAL
        else:
            state.status = InterviewStatus.RESCHEDULE_REQUIRED
        state.ended_at = time.time()
        await self.store.save(state)
        return state.status