"""
Deterministic weighted scoring against an extracted ResumeProfile.
Only the semantic-matching and project-relevance calls hit the LLM
(done upstream in extractor.py) — combining them into a final score here
is pure Python math, free and instantly re-tunable.
"""
from __future__ import annotations

from typing import Union

from . import config
from .schemas import (
    ProjectRelevanceResponse,
    ResumeProfile,
    RoleRequirements,
    ScoreBreakdown,
    SkillMatchResponse,
)


def _get_expected_years(expected: Union[float, list[float], tuple[float, ...]]) -> float:
    """Convert expected_years_experience to a single float for scoring.
    If it's a range [min, max] or (min, max), use the midpoint. If it's a single value, use it directly."""
    if isinstance(expected, (list, tuple)):
        if len(expected) == 0:
            return 1.0  # default fallback
        return sum(expected) / len(expected)  # use midpoint/average
    return expected


def _score_skills_and_certifications(
    match_response: SkillMatchResponse, role_requirements: RoleRequirements
) -> tuple[float, float, list[str], list[str]]:
    total = len(role_requirements.jd_keywords)
    if total == 0:
        return 0.0, 0.0, [], []

    skill_matches = [m for m in match_response.matches if m.matched_via == "skill"]
    cert_matches = [m for m in match_response.matches if m.matched_via == "certification"]
    matched = [m.jd_keyword for m in match_response.matches if m.matched]
    missing = [m.jd_keyword for m in match_response.matches if not m.matched]

    skill_fraction = len(skill_matches) / total
    avg_years = sum(m.estimated_years for m in skill_matches) / len(skill_matches) if skill_matches else 0.0
    expected_years = _get_expected_years(role_requirements.expected_years_experience)
    depth_ratio = min(avg_years / max(expected_years, 0.5), 1.0)
    skills_score = round(min((skill_fraction * 7.0) + (depth_ratio * 3.0), config.SCORE_MAX), 2)

    cert_fraction = len(cert_matches) / total
    certifications_score = round(min(cert_fraction * config.SCORE_MAX, config.SCORE_MAX), 2)

    return skills_score, certifications_score, matched, missing


def _score_experience(profile: ResumeProfile, role_requirements: RoleRequirements) -> float:
    expected_years = _get_expected_years(role_requirements.expected_years_experience)
    ratio = min(profile.relevant_years_experience / max(expected_years, 0.5), 1.0)
    return round(ratio * config.SCORE_MAX, 2)


def _score_education(profile: ResumeProfile) -> float:
    if not profile.education:
        return config.DEFAULT_DEGREE_SCORE
    best = config.DEFAULT_DEGREE_SCORE
    for edu in profile.education:
        degree_lower = edu.degree.lower()
        for keyword, score in config.DEGREE_LEVEL_SCORES.items():
            if keyword in degree_lower:
                best = max(best, score)
    return best


def score_resume(
    profile: ResumeProfile,
    role_requirements: RoleRequirements,
    skill_match: SkillMatchResponse,
    project_relevance: ProjectRelevanceResponse,
) -> ScoreBreakdown:
    skills_score, certifications_score, matched, missing = _score_skills_and_certifications(
        skill_match, role_requirements
    )
    experience_score = _score_experience(profile, role_requirements)
    education_score = _score_education(profile)
    projects_score = round(project_relevance.projects_score, 2)

    overall = (
        skills_score * config.SKILLS_WEIGHT
        + certifications_score * config.CERTIFICATIONS_WEIGHT
        + experience_score * config.EXPERIENCE_WEIGHT
        + education_score * config.EDUCATION_WEIGHT
        + projects_score * config.PROJECTS_WEIGHT
    )

    summary_penalty_applied = not profile.summary
    if summary_penalty_applied:
        overall -= config.SUMMARY_MISSING_PENALTY

    overall = round(max(min(overall, config.SCORE_MAX), config.SCORE_MIN), 2)

    return ScoreBreakdown(
        skills_score=skills_score,
        certifications_score=certifications_score,
        experience_score=experience_score,
        education_score=education_score,
        projects_score=projects_score,
        overall_score=overall,
        threshold_used=role_requirements.threshold,
        passed_threshold=overall >= role_requirements.threshold,
        matched_keywords=matched,
        missing_keywords=missing,
        summary_penalty_applied=summary_penalty_applied,
    )