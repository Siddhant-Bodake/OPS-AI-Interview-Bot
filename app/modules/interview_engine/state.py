"""
Structured state object for a single interview session (Module 8).

This is the single source of truth the engine reads/writes every turn.
It is persisted to Redis after every scored answer (write-through), so a
dropped call/tab never loses more than the in-flight turn.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Domain(str, Enum):
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"


class AnomalyType(str, Enum):
    NOISE = "noise"
    LONG_PAUSE = "long_pause"
    SUSPICIOUS_SOUND = "suspicious_sound"


class AnomalyEvent(BaseModel):
    """Logged, never acted on live — surfaced later on the admin panel."""
    type: AnomalyType
    timestamp: float = Field(default_factory=time.time)


class AnswerScore(BaseModel):
    """Per-answer scoring — multi-criteria, averaged."""
    relevance: float
    clarity: float
    tech_depth: float

    @property
    def average(self) -> float:
        return round((self.relevance + self.clarity + self.tech_depth) / 3, 2)


class QuestionRecord(BaseModel):
    """One entry in the pre-generated question list (from Module 4)."""
    id: str
    domain: Domain
    text: str
    is_followup: bool = False
    parent_id: Optional[str] = None  # set if this is a follow-up to another question

    asked_at: Optional[float] = None
    answer_transcript: Optional[str] = None
    answered_at: Optional[float] = None
    score: Optional[AnswerScore] = None
    followup_used: bool = False  # enforces the 1-follow-up-per-question cap
    reask_count: int = 0  # how many times this question was re-asked after a non-answer


class PendingCandidateQuestion(BaseModel):
    """A question the candidate asked mid-interview; deferred to the end."""
    text: str
    asked_at: float = Field(default_factory=time.time)
    answered_at: Optional[float] = None
    answer_text: Optional[str] = None


class InterviewStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    COMPLETED_PARTIAL = "completed_partial"  # dropped, no reconnect, but >=60% covered
    DROPPED = "dropped"          # connection lost, awaiting reconnect/retry
    ABANDONED = "abandoned"      # retry window expired
    RESCHEDULE_REQUIRED = "reschedule_required"  # <60% time covered, no resume


class InterviewState(BaseModel):
    session_id: str
    candidate_id: str
    mode: str  # "telephonic" | "web"
    scheduled_duration_seconds: int

    questions: list[QuestionRecord]
    pending_candidate_questions: list[PendingCandidateQuestion] = Field(default_factory=list)
    anomalies: list[AnomalyEvent] = Field(default_factory=list)

    current_index: int = 0
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    status: InterviewStatus = InterviewStatus.IN_PROGRESS

    # --- derived / rollup helpers ---

    def elapsed_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.ended_at or time.time()
        return end - self.started_at

    def time_coverage_ratio(self) -> float:
        if self.scheduled_duration_seconds <= 0:
            return 0.0
        return min(self.elapsed_seconds() / self.scheduled_duration_seconds, 1.0)

    def is_usable_if_dropped(self) -> bool:
        """Module 6/7 rule: >=60% of scheduled time covered => usable partial data."""
        return self.time_coverage_ratio() >= 0.6

    def domain_scores(self) -> dict[str, Optional[float]]:
        """Domain-wise average final score (technical vs behavioral)."""
        buckets: dict[Domain, list[float]] = {Domain.TECHNICAL: [], Domain.BEHAVIORAL: []}
        for q in self.questions:
            if q.score is not None:
                buckets[q.domain].append(q.score.average)
        return {
            domain.value: (round(sum(scores) / len(scores), 2) if scores else None)
            for domain, scores in buckets.items()
        }

    def current_question(self) -> Optional[QuestionRecord]:
        if 0 <= self.current_index < len(self.questions):
            return self.questions[self.current_index]
        return None