"""
Pydantic models for Module 2.

ResumeProfile is the LLM extraction output — this MUST stay schema-consistent
with what Module 4 (question generation) expects, since Module 4 consumes
this same structured output.
"""
from __future__ import annotations

from typing import Optional, Literal, Union

from pydantic import BaseModel, Field


class SkillEntry(BaseModel):
    name: str
    years_experience: float = 0.0  # LLM's best estimate from context clues


class WorkExperience(BaseModel):
    company: str
    role_title: str
    start_date: Optional[str] = None   # kept as free text — resume dates are messy
    end_date: Optional[str] = None     # None or "Present"
    description: Optional[str] = None


class EducationEntry(BaseModel):
    degree: str
    institution: str
    field_of_study: Optional[str] = None
    graduation_year: Optional[int] = None


class CertificationEntry(BaseModel):
    name: str
    issuer: Optional[str] = None
    date: Optional[str] = None


class ProjectEntry(BaseModel):
    name: str
    description: Optional[str] = None
    technologies: list[str] = Field(default_factory=list)


class ResumeProfile(BaseModel):
    """LLM extraction output. Shared schema with Module 4."""
    candidate_name: Optional[str] = None
    summary: Optional[str] = None  # professional summary/objective
    skills: list[SkillEntry] = Field(default_factory=list)
    work_experience: list[WorkExperience] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    certifications: list[CertificationEntry] = Field(default_factory=list)

    # LLM-estimated, given the target role/JD as context at extraction time —
    # deliberately NOT computed from date parsing, since resume dates are too
    # inconsistent to parse reliably. This is what feeds the experience score.
    relevant_years_experience: float = 0.0


class RoleRequirements(BaseModel):
    """Config, not LLM output — one of these per job role."""
    role: str
    jd_keywords: list[str]      # skills/terms this role cares about
    expected_years_experience: Union[float, list[float]]  # single value or range [min, max]
    threshold: float            # configurable per role (locked decision)


class ScoreBreakdown(BaseModel):
    skills_score: float
    certifications_score: float
    experience_score: float
    education_score: float
    projects_score: float
    other_bonus_applied: float          # NEW
    overall_score: float
    threshold_used: float
    passed_threshold: bool
    matched_keywords: list[str]
    missing_keywords: list[str]
    summary_penalty_applied: bool   # NEW


class SkillMatch(BaseModel):
    jd_keyword: str
    matched: bool
    matched_via: Literal["skill", "certification", "none"] = "none"
    matched_candidate_skill: Optional[str] = None
    estimated_years: float = 0.0


class SkillMatch(BaseModel):
    jd_keyword: str
    matched: bool
    matched_via: Literal["skill", "certification", "none"] = "none"
    matched_candidate_skill: Optional[str] = None
    estimated_years: float = 0.0


class ScoringResponse(BaseModel):
    summary_relevance_percent: float          # Task 1 — 0 if no summary present
    skill_matches: list[SkillMatch]            # Task 2
    project_relevance: list[ProjectRelevance]  # Task 3
    experience_relevance_percent: float        # Task 4 — 0-100
    other_bonus_score: float                   # Task 5 — 0 to MAX_OTHER_BONUS


class SkillMatchResponse(BaseModel):
    matches: list[SkillMatch]


class ProjectRelevance(BaseModel):
    project_name: str
    relevance_percent: float  # 0-100
    

class ProjectRelevanceResponse(BaseModel):
    projects_score: float  # 0-10, LLM's overall judgment of relevance + depth vs the JD