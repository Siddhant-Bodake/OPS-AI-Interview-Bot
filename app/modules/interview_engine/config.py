"""Tunable constants for Module 8. Keep these config-driven, not hardcoded
inline elsewhere, so they can move to env vars / a settings table later."""

GEMINI_MODEL = "gemini-3.5-flash-lite"  # POC choice — confirm current availability before shipping

MAX_FOLLOWUPS_PER_QUESTION = 1     # locked decision: capped, not LLM's free discretion
SCORE_MIN = 0.0
SCORE_MAX = 10.0

# Module 6 / Module 7 shared rule: partial data below this coverage requires
# a full reschedule instead of being treated as usable.
MIN_TIME_COVERAGE_FOR_USABLE_PARTIAL = 0.6

REASK_MAX_CAP = 2  # after this many re-asks on the same question, accept the low score and move on

# Free-tier Gemini is RPM-limited (e.g. 15/min). Space out calls so a normal
# interview session never gets 429'd. 4.5s spacing keeps you under 15/min
# with headroom; bump this via env/config if your quota is different.
MIN_SECONDS_BETWEEN_GEMINI_CALLS = 0.0