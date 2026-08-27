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
    supporting keywords (tooling/db/devops) — with 3 phases based on seniority:
    - Fresher (1-3 years): core = supporting (equal weights)
    - Mid (3-6 years): core = 1.0, supporting = 0.7
    - Expert (6+ years): core = 1.0, supporting = 0.5"""
    expected_years = _get_expected_years(role_requirements.expected_years_experience)
    
    if expected_years < 3:
        # Fresher phase: equal weights
        if keyword in role_requirements.core_keywords:
            return 1.0
        return 1.0
    elif expected_years < 6:
        # Mid phase: core weighted higher
        if keyword in role_requirements.core_keywords:
            return 1.0
        return 0.7
    else:
        # Expert phase: core and supporting both lower but core still higher
        if keyword in role_requirements.core_keywords:
            return 1.0
        return 0.5


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


def _score_experience(
    profile: ResumeProfile,
    role_requirements: RoleRequirements,
    scoring: ScoringResponse,
) -> float:
    """Score experience based on LLM relevance AND sufficiency against expected years range."""
    experience_score = round(scoring.experience_relevance_percent / 100 * config.SCORE_MAX, 2)
    
    expected = role_requirements.expected_years_experience
    candidate_years = profile.relevant_years_experience or 0.0
    
    # Determine comparison point based on range logic
    if isinstance(expected, list):
        if len(expected) >= 2:
            min_expected, max_expected = expected[0], expected[1]
            # If below minimum, compare against minimum
            # If at or above minimum, compare against maximum (for seniority assessment)
            comparison_point = min_expected if candidate_years < min_expected else max_expected
        else:
            comparison_point = expected[0] if expected else 1.0
    else:
        comparison_point = expected
    
    # Apply fixed penalties based on sufficiency
    if candidate_years < comparison_point * 0.5:
        # Less than 50% - heavy penalty
        return round(experience_score - 1.25, 2)
    elif candidate_years < comparison_point * 0.75:
        # Less than 75% - moderate penalty
        return round(experience_score - 0.5, 2)
    
    return experience_score


def score_resume(
    profile: ResumeProfile,
    role_requirements: RoleRequirements,
    scoring: ScoringResponse,
) -> ScoreBreakdown:
    skills_score, certifications_score, matched, missing = _score_skills_and_certifications(
        scoring, role_requirements
    )
    experience_score = _score_experience(profile, role_requirements, scoring)
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