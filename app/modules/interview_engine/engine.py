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

import time
import uuid

from google import genai
from google.genai import types

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

    # ---------------------------------------------------------------- setup

    def new_session(
        self,
        candidate_id: str,
        mode: str,
        scheduled_duration_seconds: int,
        question_bank: list[dict],
    ) -> InterviewState:
        """question_bank entries: {"id", "domain", "text"} — from Module 4 output."""
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

    async def _generate(self, prompt: str, schema: type):
        response = await self.client.aio.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        return response.parsed  # already a validated instance of `schema`

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
        """Never interrupts the live flow — logged and persisted immediately
        so an anomaly is never lost to a drop before the next scored answer."""
        state.anomalies.append(AnomalyEvent(type=anomaly_type))
        await self.store.save(state)

    async def queue_candidate_question(self, state: InterviewState, question_text: str) -> None:
        """Mid-interview candidate question — deferred, answered at the end.
        Persisted immediately, same reasoning as log_anomaly above."""
        state.pending_candidate_questions.append(PendingCandidateQuestion(text=question_text))
        await self.store.save(state)

    # --------------------------------------------------------- answer intake

    async def handle_answer(
        self, state: InterviewState, role: str, answer_transcript: str
    ) -> dict:
        """
        Scores the current question's answer, decides on a capped follow-up,
        persists state, and returns what should happen next.
        """
        question = state.current_question()
        if question is None:
            raise ValueError("No current question to answer — interview may already be complete.")

        persona = prompts.INTERVIEWER_PERSONA.format(role=role)

        # 1. Score the answer.
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

        # 2. Decide on a follow-up, only if the per-question budget allows it.
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

        # 3. Write-through persistence — the whole point of the exercise.
        await self.store.save(state)

        return {
            "action": next_action,
            "followup_text": followup_text,
            "next_question": state.current_question().text if state.current_question() else None,
        }

    # ------------------------------------------------------------- wrap-up

    async def close_out(self, state: InterviewState, role: str, jd_context: str) -> str:
        """Answers any deferred candidate questions briefly, finalizes state."""
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
        """Called when the call/session disconnects mid-interview (Module 6/7)."""
        state.status = InterviewStatus.DROPPED
        await self.store.save(state)
        return state.status

    async def resume(self, session_id: str) -> InterviewState | None:
        """Called on a successful reconnect — picks up exactly where it left off."""
        state = await self.store.load(session_id)
        if state is None:
            return None
        state.status = InterviewStatus.IN_PROGRESS
        await self.store.save(state)
        return state

    async def finalize_after_failed_reconnect(self, state: InterviewState) -> InterviewStatus:
        """Called once the retry window is exhausted with no reconnect."""
        if state.is_usable_if_dropped():
            # Partial but usable per the 60% rule — kept distinct from a full
            # completion so the admin panel (Module 10) can tell them apart.
            state.status = InterviewStatus.COMPLETED_PARTIAL
        else:
            state.status = InterviewStatus.RESCHEDULE_REQUIRED
        state.ended_at = time.time()
        await self.store.save(state)
        return state.status