from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class QuestionGenConfig(BaseModel):
    """Per-role question generation config. Falls back to static defaults if not provided."""
    technical_split: float = 0.7
    behavioral_split: float = 0.3
    base_question_count: int = 20
    years_divisor: float = 0.5
    max_question_count: int = 25
    bank_question_ratio: float = 0.3
    technical_type_ratio: dict[str, float] = Field(
        default_factory=lambda: {"core": 0.4, "database": 0.4, "scenario_based": 0.2}
    )
    enforce_exact_counts: bool = True
    enforce_type_coverage: bool = True
    deduplication_enabled: bool = True


class GeneratedQuestion(BaseModel):
    domain: Literal["technical", "behavioral"]
    text: str
    source: Literal["bank", "generated"]
    title: str = ""
    follow_up: str = ""
    difficulty: str = "medium"
    expected_concepts: list[str] = []
    type: str = ""


class QuestionGenerationResponse(BaseModel):
    questions: list[GeneratedQuestion]