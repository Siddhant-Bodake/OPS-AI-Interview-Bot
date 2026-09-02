from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator, model_validator

from app.modules.candidate_form.enums import EmploymentStatus, HearAboutSource, WorkMode

PHONE_PATTERN = re.compile(r"^\+?[\d\s\-()]{7,20}$")


class CandidateFormCreate(BaseModel):
    email_address: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    phone_number: str = Field(min_length=7, max_length=20)
    current_location: str = Field(min_length=1, max_length=200)
    applied_role_id: str | None = Field(default=None, max_length=36)
    applied_role_other: str | None = Field(default=None, max_length=200)
    total_experience_years: Decimal = Field(ge=0)
    relevant_experience_years: Decimal = Field(ge=0)
    primary_skills: list[str] = Field(min_length=1, max_length=5)
    certifications: list[str] = Field(default_factory=list, max_length=5)
    employment_status: EmploymentStatus
    notice_period: str | None = Field(default=None, max_length=100)
    available_from: date
    preferred_work_mode: WorkMode
    willing_to_relocate: bool
    current_ctc_lpa: Decimal = Field(ge=0)
    expected_ctc_lpa: Decimal = Field(ge=0)
    interest_reason: str = Field(min_length=1)
    linkedin_portfolio_url: HttpUrl | None = None
    hear_about: HearAboutSource
    hear_about_other: str | None = Field(default=None, max_length=200)
    consent_given: bool

    @field_validator(
        "applied_role_id",
        "notice_period",
        "hear_about_other",
        mode="before",
    )
    @classmethod
    def empty_str_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("primary_skills", "certifications", mode="before")
    @classmethod
    def normalize_string_lists(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            value = [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            cleaned = [item.strip() for item in value if isinstance(item, str) and item.strip()]
            return cleaned
        return value

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        if not PHONE_PATTERN.match(value):
            raise ValueError("Invalid phone number format")
        return value

    @field_validator("total_experience_years", "relevant_experience_years", "current_ctc_lpa", "expected_ctc_lpa")
    @classmethod
    def validate_decimal_places(cls, value: Decimal) -> Decimal:
        if value.as_tuple().exponent < -2:
            raise ValueError("At most 2 decimal places allowed")
        return value

    @model_validator(mode="after")
    def validate_cross_fields(self) -> Self:
        if self.relevant_experience_years > self.total_experience_years:
            raise ValueError("Relevant experience cannot exceed total experience")

        has_role_id = self.applied_role_id is not None
        has_role_other = self.applied_role_other is not None and self.applied_role_other.strip() != ""
        if has_role_id == has_role_other:
            raise ValueError("Provide exactly one of applied_role_id or applied_role_other")

        if self.employment_status == EmploymentStatus.EMPLOYED:
            if not self.notice_period or not self.notice_period.strip():
                raise ValueError("Notice period is required when employment status is employed")
        elif self.notice_period is not None and self.notice_period.strip():
            raise ValueError("Notice period must be empty unless employment status is employed")

        if self.available_from < date.today():
            raise ValueError("Available from must be today or a future date")

        if self.hear_about == HearAboutSource.OTHER:
            if not self.hear_about_other or not self.hear_about_other.strip():
                raise ValueError("hear_about_other is required when hear_about is other")
        elif self.hear_about_other is not None and self.hear_about_other.strip():
            raise ValueError("hear_about_other must be empty unless hear_about is other")

        if not self.consent_given:
            raise ValueError("Consent must be given to submit the form")

        return self


class CandidateFormRecord(BaseModel):
    id: UUID
    candidate_id: UUID
    email_address: str
    full_name: str
    phone_number: str
    current_location: str
    applied_role_id: str | None
    applied_role_other: str | None
    applied_role_display: str
    total_experience_years: Decimal
    relevant_experience_years: Decimal
    primary_skills: list[str]
    certifications: list[str]
    employment_status: EmploymentStatus
    notice_period: str | None
    available_from: date
    preferred_work_mode: WorkMode
    willing_to_relocate: bool
    current_ctc_lpa: Decimal
    expected_ctc_lpa: Decimal
    interest_reason: str
    linkedin_portfolio_url: str | None
    hear_about: HearAboutSource
    hear_about_other: str | None
    consent_given: bool
    created_at: datetime


class CandidateFormSubmitResponse(BaseModel):
    id: UUID
    candidate_id: UUID
    message: str
    created_at: datetime
