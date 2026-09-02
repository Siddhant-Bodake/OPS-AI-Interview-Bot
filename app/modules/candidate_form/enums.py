from __future__ import annotations

from enum import StrEnum


class EmploymentStatus(StrEnum):
    EMPLOYED = "employed"
    UNEMPLOYED = "unemployed"
    STUDENT = "student"


class WorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ON_SITE = "on_site"


class HearAboutSource(StrEnum):
    LINKEDIN = "linkedin"
    REFERRAL = "referral"
    COMPANY_WEBSITE = "company_website"
    JOB_PORTAL = "job_portal"
    RECRUITER = "recruiter"
    OTHER = "other"
