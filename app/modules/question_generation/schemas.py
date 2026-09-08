from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GeneratedQuestion(BaseModel):
    domain: Literal["technical", "behavioral"]
    text: str
    source: Literal["bank", "generated"]


class QuestionGenerationResponse(BaseModel):
    questions: list[GeneratedQuestion]