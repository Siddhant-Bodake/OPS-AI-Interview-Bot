"""Deterministic scoring from an LLM-judged ScoringResponse. All the
relevance judgment happens upstream in one Gemini call; this is pure
Python math turning it into the weighted final score."""
from __future__ import annotations

from typing import Union

from . import config
from .schemas import ResumeProfile, RoleRequirements, ScoreBreakdown, ScoringResponse


def _get_expected_years(expected: Union[float, list[float]]) -> float:
    """Convert expected_years_experience to a single float for scoring.
    If it's a range [min, max], use the midpoint. If it's a single value, use it directly."""
    if isinstance(expected, list):
        if len(expected) == 0:
            return 1.0  # default fallback
        return sum(expected) / len(expected)  # use midpoint/average
    return expected


def _keyword_weight(keyword: str, role_requirements: RoleRequirements) -> float:
    """Core keywords (language/framework/architecture) are weighted more than
    supporting keywords (tooling/db/devops) — and that gap widens as the
    role expects more seniority. At 0 years expected, core = supporting
    weight (1.0 vs 0.5, so core still counts double). At 10+ years expected,
    core weight doubles again (up to 2.0x base), so architecture/framework
    depth dominates the skills score far more than tooling for senior roles."""

    expected_years = _get_expected_years(role_requirements.expected_years_experience)
    seniority_multiplier = 1.0 + min(expected_years / 5.0, 1.0)
    if keyword in role_requirements.core_keywords:
        return 1.0 * seniority_multiplier
    return 0.5  # supporting keywords stay flat regardless of seniority


def _score_skills_and_certifications(
    scoring: ScoringResponse, role_requirements: RoleRequirements
) -> tuple[float, float, list[str], list[str]]:
    all_keywords = role_requirements.core_keywords + role_requirements.supporting_keywords
    total_weight = sum(_keyword_weight(k, role_requirements) for k in all_keywords)
    if total_weight == 0:
        return 0.0, 0.0, [], []

    matched = [m.jd_keyword for m in scoring.skill_matches if m.matched]
    missing = [m.jd_keyword for m in scoring.skill_matches if not m.matched]
    skill_matches = [m for m in scoring.skill_matches if m.matched_via == "skill"]

    matched_skill_weight = sum(
        _keyword_weight(m.jd_keyword, role_requirements) for m in skill_matches
    )
    skill_fraction = matched_skill_weight / total_weight
    avg_years = sum(m.estimated_years for m in skill_matches) / len(skill_matches) if skill_matches else 0.0
    expected_years = _get_expected_years(role_requirements.expected_years_experience)
    depth_ratio = min(avg_years / max(expected_years, 0.5), 1.0)
    skills_score = round(min((skill_fraction * 7.0) + (depth_ratio * 3.0), config.SCORE_MAX), 2)

    cert_matches = [m for m in scoring.skill_matches if m.matched_via == "certification"]
    matched_cert_weight = sum(_keyword_weight(m.jd_keyword, role_requirements) for m in cert_matches)
    cert_fraction = matched_cert_weight / total_weight
    certifications_score = round(min(cert_fraction * config.SCORE_MAX, config.SCORE_MAX), 2)

    return skills_score, certifications_score, matched, missing


def _score_projects(scoring: ScoringResponse) -> float:
    relevant_count = sum(
        1 for p in scoring.project_relevance if p.relevance_percent >= config.PROJECT_RELEVANCE_THRESHOLD
    )
    if relevant_count >= 2:
        return config.SCORE_MAX
    if relevant_count == 1:
        return round(config.SCORE_MAX * 0.5, 2)
    return 0.0


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
    scoring: ScoringResponse,
) -> ScoreBreakdown:
    skills_score, certifications_score, matched, missing = _score_skills_and_certifications(
        scoring, role_requirements
    )
    experience_score = round(scoring.experience_relevance_percent / 100 * config.SCORE_MAX, 2)
    education_score = _score_education(profile)
    projects_score = _score_projects(scoring)

    overall = (
        skills_score * config.SKILLS_WEIGHT
        + certifications_score * config.CERTIFICATIONS_WEIGHT
        + experience_score * config.EXPERIENCE_WEIGHT
        + education_score * config.EDUCATION_WEIGHT
        + projects_score * config.PROJECTS_WEIGHT
    )

    summary_penalty_applied = (
        not profile.summary or scoring.summary_relevance_percent < config.SUMMARY_RELEVANCE_THRESHOLD
    )
    if summary_penalty_applied:
        overall -= config.SUMMARY_MISSING_PENALTY

    other_bonus_applied = round(min(max(scoring.other_bonus_score, 0.0), config.MAX_OTHER_BONUS), 2)
    overall += other_bonus_applied

    overall = round(max(min(overall, config.SCORE_MAX), config.SCORE_MIN), 2)

    return ScoreBreakdown(
        skills_score=skills_score,
        certifications_score=certifications_score,
        experience_score=experience_score,
        education_score=education_score,
        projects_score=projects_score,
        other_bonus_applied=other_bonus_applied,
        overall_score=overall,
        threshold_used=role_requirements.threshold,
        passed_threshold=overall >= role_requirements.threshold,
        matched_keywords=matched,
        missing_keywords=missing,
        summary_penalty_applied=summary_penalty_applied,
    )