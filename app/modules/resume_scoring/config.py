"""Tunable constants for Module 2 (resume parsing & scoring)."""


# GEMINI_MODEL = "gemma-4-31b-it"
GEMINI_MODEL = "gemma-4-26b-a4b-it"
# GEMINI_MODEL = "gemini-3.5-flash-lite"
MIN_SECONDS_BETWEEN_GEMINI_CALLS = 0.0  # same free-tier RPM guard as module 8


SUPPORTED_RESUME_FORMATS = {".pdf", ".docx"}


# Weighted formula — configurable, sums to 1.0. Locked distribution:
# skills 30 + certifications 5 (35 combined) / experience 25 / education 15 / projects 25
SKILLS_WEIGHT = 0.30
CERTIFICATIONS_WEIGHT = 0.05
EXPERIENCE_WEIGHT = 0.25
EDUCATION_WEIGHT = 0.15
PROJECTS_WEIGHT = 0.25


SCORE_MIN = 0.0
SCORE_MAX = 10.0


# Simple degree-level ranking for the education score heuristic.
DEGREE_LEVEL_SCORES = {
    "phd": 10.0, "doctorate": 10.0, "ph.d": 10.0,
    "master": 8.0, "m.s": 8.0, "m.a": 8.0, "mba": 8.0,
    "bachelor": 6.0, "b.s": 6.0, "b.a": 6.0, "b.sc": 6.0, "undergraduate": 6.0, "b.tech": 6.0,
    "associate": 4.0, "a.s": 4.0, "a.a": 4.0,
}
DEFAULT_DEGREE_SCORE = 4.0  # unrecognized/other/no degree


# Missing-summary penalty: deducted from the final overall score (not a
# weighted dimension — summary itself stays unscored/contextual).
SUMMARY_MISSING_PENALTY = 0.5