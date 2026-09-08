"""Determines a candidate's seniority tier from their relevant years of
experience, using the role's configurable seniority_bands."""
from __future__ import annotations


def determine_seniority_tier(relevant_years: float, seniority_bands) -> str:
    # Handle single JSONB object from DB: {"tier": "mid", "min_years": 2, "max_years": 5}
    if isinstance(seniority_bands, dict):
        return seniority_bands.get("tier", "mid")

    # Handle list of band dicts (original spec format)
    for band in seniority_bands:
        min_years = band["min_years"]
        max_years = band["max_years"]  # None means unbounded (e.g. senior: 5+)
        if relevant_years >= min_years and (max_years is None or relevant_years < max_years):
            return band["tier"]
    return seniority_bands[-1]["tier"]  # fallback: highest tier if nothing matched


def question_count_for(relevant_years: float, base: float, divisor: float, cap: int) -> int:
    count = base + (relevant_years / divisor)
    return min(round(count), cap)