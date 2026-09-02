from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import streamlit as st

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from streamlit_app.api_client import CandidateFormApiError, fetch_roles, submit_application

PHONE_PATTERN = re.compile(r"^\+?[\d\s\-()]{7,20}$")
HEAR_ABOUT_OPTIONS = {
    "LinkedIn": "linkedin",
    "Referral": "referral",
    "Company Website": "company_website",
    "Job Portal": "job_portal",
    "Recruiter": "recruiter",
    "Other": "other",
}
EMPLOYMENT_OPTIONS = {
    "Employed": "employed",
    "Unemployed": "unemployed",
    "Student": "student",
}
WORK_MODE_OPTIONS = {
    "Remote": "remote",
    "Hybrid": "hybrid",
    "On-site": "on_site",
}


def query_email() -> str | None:
    params = st.query_params
    raw = params.get("email") or params.get("email_address")
    if raw is None:
        return None
    value = raw[0] if isinstance(raw, list) else raw
    value = value.strip()
    return value or None


def validate_client(payload: dict, hear_about_label: str) -> list[str]:
    errors: list[str] = []
    if not payload["email_address"]:
        errors.append("Email address is required.")
    if len(payload["full_name"].strip()) < 2:
        errors.append("Full name must be at least 2 characters.")
    if not PHONE_PATTERN.match(payload["phone_number"]):
        errors.append("Enter a valid phone number.")
    if not payload["current_location"].strip():
        errors.append("Current location is required.")
    if not payload["applied_role_id"]:
        errors.append("Please select an applied role.")
    if payload["relevant_experience_years"] > payload["total_experience_years"]:
        errors.append("Relevant experience cannot exceed total experience.")
    if payload["employment_status"] == "employed" and not (payload["notice_period"] or "").strip():
        errors.append("Notice period is required when you are employed.")
    if payload["available_from"] < date.today().isoformat():
        errors.append("Available from must be today or a future date.")
    if not payload["primary_skills"]:
        errors.append("Add at least one primary / key skill (max 5).")
    elif len(payload["primary_skills"]) > 5:
        errors.append("You can add at most 5 primary / key skills.")
    if len(payload["certifications"]) > 5:
        errors.append("You can add at most 5 certifications.")
    if not payload["interest_reason"].strip():
        errors.append("Please tell us why you are interested in this role.")
    if hear_about_label == "Other" and not (payload["hear_about_other"] or "").strip():
        errors.append("Please specify how you heard about this opportunity.")
    if not payload["consent_given"]:
        errors.append("You must give consent to submit the form.")
    return errors


st.set_page_config(page_title="Candidate Application Form", layout="centered")
st.title("Candidate Application Form")
st.caption("Fields marked with * are required.")

prefilled_email = query_email()

try:
    roles_data = fetch_roles()
    role_options = {role["id"]: role["name"] for role in roles_data}
    role_labels = list(role_options.values())
    role_id_by_label = {label: role_id for role_id, label in role_options.items()}
except CandidateFormApiError as exc:
    st.error(f"Failed to load available roles: {exc.detail}")
    st.stop()

email_address = st.text_input(
    "Email Address *",
    value=prefilled_email or "",
    disabled=prefilled_email is not None,
)
applied_role_label = st.selectbox("Applied Role *", role_labels)

employment_label = st.radio("Employment Status *", list(EMPLOYMENT_OPTIONS.keys()), horizontal=True)
notice_period = ""
if employment_label == "Employed":
    notice_period = st.text_input("Notice Period *")

hear_about_label = st.selectbox("How did you hear about this opportunity? *", list(HEAR_ABOUT_OPTIONS.keys()))
hear_about_other = ""
if hear_about_label == "Other":
    hear_about_other = st.text_input("Please specify *")

with st.form("candidate_application"):
    full_name = st.text_input("Full Name *")
    phone_number = st.text_input("Phone Number *")
    current_location = st.text_input("Current Location *")
    total_experience_years = st.number_input("Total Experience (years) *", min_value=0.0, step=0.5, format="%.1f")
    relevant_experience_years = st.number_input(
        "Relevant Experience (years) *",
        min_value=0.0,
        step=0.5,
        format="%.1f",
    )
    primary_skills = st.multiselect(
        "Primary / Key Skills * (max 5)",
        options=[],
        accept_new_options=True,
        max_selections=5,
        help="Type a skill and press Enter. Up to 5 skills.",
    )
    certifications = st.multiselect(
        "Certifications (max 5)",
        options=[],
        accept_new_options=True,
        max_selections=5,
        help="Optional. Type a certification and press Enter. Up to 5.",
    )
    available_from = st.date_input("Available From (Tentative Date) *", min_value=date.today())
    preferred_work_mode_label = st.radio("Preferred Work Mode *", list(WORK_MODE_OPTIONS.keys()), horizontal=True)
    relocate_label = st.radio("Willing to Relocate? *", ["Yes", "No"], horizontal=True)
    current_ctc_lpa = st.number_input("Current CTC (LPA) *", min_value=0.0, step=0.1, format="%.2f")
    expected_ctc_lpa = st.number_input("Expected CTC (LPA) *", min_value=0.0, step=0.1, format="%.2f")
    interest_reason = st.text_area(
        "Why are you interested in this role, or what are you looking for in your next role? *"
    )
    linkedin_portfolio_url = st.text_input("LinkedIn / Portfolio URL")
    consent_given = st.checkbox("I consent to the processing of my information for this application. *")
    submitted = st.form_submit_button("Submit application")

if submitted:
    payload = {
        "email_address": (prefilled_email or email_address).strip(),
        "full_name": full_name.strip(),
        "phone_number": phone_number.strip(),
        "current_location": current_location.strip(),
        "applied_role_id": role_id_by_label[applied_role_label],
        "total_experience_years": total_experience_years,
        "relevant_experience_years": relevant_experience_years,
        "primary_skills": [skill.strip() for skill in primary_skills if skill.strip()],
        "certifications": [cert.strip() for cert in certifications if cert.strip()],
        "employment_status": EMPLOYMENT_OPTIONS[employment_label],
        "notice_period": notice_period.strip() or None,
        "available_from": available_from.isoformat(),
        "preferred_work_mode": WORK_MODE_OPTIONS[preferred_work_mode_label],
        "willing_to_relocate": relocate_label == "Yes",
        "current_ctc_lpa": current_ctc_lpa,
        "expected_ctc_lpa": expected_ctc_lpa,
        "interest_reason": interest_reason.strip(),
        "linkedin_portfolio_url": linkedin_portfolio_url.strip() or None,
        "hear_about": HEAR_ABOUT_OPTIONS[hear_about_label],
        "hear_about_other": hear_about_other.strip() or None,
        "consent_given": consent_given,
    }
    errors = validate_client(payload, hear_about_label)
    if errors:
        for error in errors:
            st.error(error)
    else:
        try:
            result = submit_application(payload)
            st.success(
                f"{result.get('message', 'Application submitted successfully')} "
                f"(candidate_id: {result.get('candidate_id')})"
            )
        except CandidateFormApiError as exc:
            if exc.status_code == 404:
                st.error("We couldn't find your profile. Please use the email you registered with.")
            else:
                st.error(exc.detail)
