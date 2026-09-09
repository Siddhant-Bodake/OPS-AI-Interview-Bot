"""Tunable constants for Module 4 (AI question generation)."""

GEMINI_MODEL = "gemini-3.5-flash"
MIN_SECONDS_BETWEEN_GEMINI_CALLS = 1.0

# Locked decisions from spec:
TECHNICAL_SPLIT = 0.7   # fixed 60/40 technical/behavioral mix
BEHAVIORAL_SPLIT = 0.3

BASE_QUESTION_COUNT = 20    # count formula: base + years/2, capped
YEARS_DIVISOR = 0.5
MAX_QUESTION_COUNT = 25

# Bank-vs-generated mix within the final question set
BANK_QUESTION_RATIO = 0.3  # ~50% pulled from the bank as-is, ~50% resume-personalized

# Technical type distribution (core:database:scenario_based)
TECHNICAL_TYPE_RATIO = {"core": 0.4, "database": 0.4, "scenario_based": 0.2}

# Validation flags
ENFORCE_EXACT_COUNTS = True
ENFORCE_TYPE_COVERAGE = True
DEDUPLICATION_ENABLED = True