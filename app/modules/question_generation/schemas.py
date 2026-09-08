from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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