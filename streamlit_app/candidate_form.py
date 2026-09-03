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
    "Instagram": "instagram",
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


def validate_client(payload: dict, hear_about_label: str) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not payload["email_address"]:
        errors["Email Address"] = "Email address is required."
    if len(payload["full_name"].strip()) < 2:
        errors["Full Name"] = "Full name is required."
    if not PHONE_PATTERN.match(payload["phone_number"]):
        errors["Phone Number"] = "Enter a valid phone number."
    if not payload["current_location"].strip():
        errors["Current Location"] = "Current location is required."
    if not payload["applied_role_id"]:
        errors["Applied Role"] = "Please select an applied role."
    if payload["relevant_experience_years"] > payload["total_experience_years"]:
        errors["Relevant Experience"] = "Relevant experience cannot exceed total experience."
    if payload["employment_status"] == "employed" and not (payload["notice_period"] or "").strip():
        errors["Notice Period"] = "Notice period is required for employed candidates."
    if payload["available_from"] < date.today().isoformat():
        errors["Available From"] = "Available from must be today or a future date."
    if not payload["primary_skills"]:
        errors["Primary Skills"] = "Add at least one primary / key skill (max 5)."
    elif len(payload["primary_skills"]) > 5:
        errors["Primary Skills"] = "You can add at most 5 primary / key skills."
    if len(payload["certifications"]) > 5:
        errors["Certifications"] = "You can add at most 5 certifications."
    if not payload["interest_reason"].strip():
        errors["Interest Reason"] = "Please tell us why you are interested in this role."
    if hear_about_label == "Other" and not (payload["hear_about_other"] or "").strip():
        errors["How you heard about us"] = "Please specify how you heard about this opportunity."
    if not payload["consent_given"]:
        errors["Consent"] = "You must give consent to submit the form."
    return errors


st.set_page_config(page_title="Candidate Application Form", layout="centered")
st.title("Candidate Application Form")
st.caption("Fields marked with * are required.")

# Initialize session state for errors
if "form_errors" not in st.session_state:
    st.session_state.form_errors = {}
if "form_submitted" not in st.session_state:
    st.session_state.form_submitted = False

prefilled_email = query_email()

try:
    roles_data = fetch_roles()
    role_options = {role["id"]: role["name"] for role in roles_data}
    role_labels = list(role_options.values())
    role_id_by_label = {label: role_id for role_id, label in role_options.items()}
except CandidateFormApiError as exc:
    st.error(f"Failed to load available roles: {exc.detail}")
    st.stop()

with st.form("candidate_application"):
    st.markdown("---")
    st.subheader("📋 Personal Information")

    email_address = st.text_input(
        "Email Address *",
        value=prefilled_email or "",
        disabled=prefilled_email is not None,
    )
    if st.session_state.form_submitted and "Email Address" in st.session_state.form_errors:
        st.error(st.session_state.form_errors["Email Address"])

    full_name = st.text_input("Full Name *")
    if st.session_state.form_submitted and "Full Name" in st.session_state.form_errors:
        st.error(st.session_state.form_errors["Full Name"])

    phone_number = st.text_input("Phone Number *")
    if st.session_state.form_submitted and "Phone Number" in st.session_state.form_errors:
        st.error(st.session_state.form_errors["Phone Number"])

    current_location = st.text_input("Current Location *")
    if st.session_state.form_submitted and "Current Location" in st.session_state.form_errors:
        st.error(st.session_state.form_errors["Current Location"])

    st.markdown("---")

    applied_role_label = st.selectbox("Applied Role *", role_labels)
    if st.session_state.form_submitted and "Applied Role" in st.session_state.form_errors:
        st.error(st.session_state.form_errors["Applied Role"])

    employment_label = st.radio("Employment Status *", list(EMPLOYMENT_OPTIONS.keys()), horizontal=True)
    notice_period = st.text_input(
        "Notice Period *",
        disabled=employment_label != "Employed",
        placeholder="e.g., 30 days or NA",
    )
    if st.session_state.form_submitted and "Notice Period" in st.session_state.form_errors:
        st.error(st.session_state.form_errors["Notice Period"])

    st.markdown("---")
    st.subheader("📊 Experience & Skills")

    total_experience_years = st.number_input("Total Experience (years) *", min_value=0.0, step=0.5, format="%.1f")
    relevant_experience_years = st.number_input(
        "Relevant Experience (years) *",
        min_value=0.0,
        step=0.5,
        format="%.1f",
    )
    if st.session_state.form_submitted and "Relevant Experience" in st.session_state.form_errors:
        st.error(st.session_state.form_errors["Relevant Experience"])

    primary_skills = st.multiselect(
        "Primary / Key Skills * (max 5)",
        options=[],
        accept_new_options=True,
        max_selections=5,
        help="Type a skill and press Enter. Up to 5 skills.",
    )
    if st.session_state.form_submitted and "Primary Skills" in st.session_state.form_errors:
        st.error(st.session_state.form_errors["Primary Skills"])

    certifications = st.multiselect(
        "Certifications (max 5)",
        options=[],
        accept_new_options=True,
        max_selections=5,
        help="Optional. Type a certification and press Enter. Up to 5.",
    )
    if st.session_state.form_submitted and "Certifications" in st.session_state.form_errors:
        st.error(st.session_state.form_errors["Certifications"])

    st.markdown("---")
    st.subheader("📅 Availability & Preferences")

    available_from = st.date_input("Available From (Tentative Date) *", min_value=date.today())
    if st.session_state.form_submitted and "Available From" in st.session_state.form_errors:
        st.error(st.session_state.form_errors["Available From"])

    preferred_work_mode_label = st.radio("Preferred Work Mode *", list(WORK_MODE_OPTIONS.keys()), horizontal=True)
    relocate_label = st.radio("Willing to Relocate? *", ["Yes", "No"], horizontal=True)

    st.markdown("---")
    st.subheader("💰 Compensation")

    current_ctc_lpa = st.number_input("Current CTC (LPA) *", min_value=0.0, step=0.1, format="%.2f")
    expected_ctc_lpa = st.number_input("Expected CTC (LPA) *", min_value=0.0, step=0.1, format="%.02f")

    st.markdown("---")
    st.subheader("📝 Additional Information")

    interest_reason = st.text_area(
        "Why are you interested in this role, or what are you looking for in your next role? *"
    )
    if st.session_state.form_submitted and "Interest Reason" in st.session_state.form_errors:
        st.error(st.session_state.form_errors["Interest Reason"])

    linkedin_portfolio_url = st.text_input("LinkedIn / Portfolio URL")

    hear_about_label = st.selectbox("How did you hear about this opportunity? *", list(HEAR_ABOUT_OPTIONS.keys()))
    hear_about_other = ""
    if hear_about_label == "Other":
        hear_about_other = st.text_input("Please specify *")
        if st.session_state.form_submitted and "How you heard about us" in st.session_state.form_errors:
            st.error(st.session_state.form_errors["How you heard about us"])

    st.markdown("---")
    consent_given = st.checkbox("I consent to the processing of my information for this application. *")
    if st.session_state.form_submitted and "Consent" in st.session_state.form_errors:
        st.error(st.session_state.form_errors["Consent"])

    submitted = st.form_submit_button("Submit Application", use_container_width=True, type="primary")

    if submitted:
        st.session_state.form_submitted = True
        if not consent_given:
            st.error("❌ Please check the consent box to submit your application.")
            st.toast("Consent required", icon="❌")
            st.session_state.form_errors = {"Consent": "You must give consent to submit the form."}
        else:
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
            st.session_state.form_errors = errors
            if errors:
                st.warning("⚠️ Please fill in the required fields.")
                st.toast("Form has validation errors", icon="⚠️")
            else:
                try:
                    result = submit_application(payload)
                    st.success("✅ Application submitted successfully!")
                    st.toast("Application submitted successfully!", icon="✅")
                    st.session_state.form_submitted = False
                    st.session_state.form_errors = {}
                    st.rerun()
                except CandidateFormApiError as exc:
                    if exc.status_code == 404:
                        st.error("❌ We couldn't find your profile. Please use the email you registered with.")
                        st.toast("Profile not found", icon="❌")
                    else:
                        st.error(f"❌ {exc.detail}")
                        st.toast("Submission failed", icon="❌")
