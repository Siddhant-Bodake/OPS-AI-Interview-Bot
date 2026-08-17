"""Structured-output schemas passed to Gemini as response_schema, so every
LLM call returns typed JSON instead of free text we'd have to parse."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ScoreResponse(BaseModel):
    relevance: float
    clarity: float
    tech_depth: float


class FollowupDecisionResponse(BaseModel):
    should_ask_followup: bool
    followup_text: Optional[str] = None


class DeferredAnswerPair(BaseModel):
    question: str
    answer: str


class DeferredQAResponse(BaseModel):
    answers: list[DeferredAnswerPair]


class GreetingResponse(BaseModel):
    greeting_text: str