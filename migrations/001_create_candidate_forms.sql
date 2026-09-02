-- Prerequisite: candidate table must already exist in the same database.
-- Reference schema:
--   CREATE TABLE candidate (
--     id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
--     email_address   VARCHAR(255) NOT NULL UNIQUE,
--     candidate_name  VARCHAR(255) NOT NULL
--   );

CREATE TYPE employment_status AS ENUM ('employed', 'unemployed', 'student');
CREATE TYPE work_mode AS ENUM ('remote', 'hybrid', 'on_site');
CREATE TYPE hear_about_source AS ENUM (
  'linkedin', 'referral', 'company_website', 'job_portal', 'recruiter', 'other'
);

CREATE TABLE candidate_forms (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id        UUID NOT NULL REFERENCES candidate(id),
  email_address       VARCHAR(255) NOT NULL,
  full_name           VARCHAR(200) NOT NULL,
  phone_number        VARCHAR(20) NOT NULL,
  current_location    VARCHAR(200) NOT NULL,

  applied_role_id     VARCHAR(36),
  applied_role_other  VARCHAR(200),
  applied_role_display VARCHAR(200) NOT NULL,

  total_experience_years    NUMERIC(4,1) NOT NULL CHECK (total_experience_years >= 0),
  relevant_experience_years NUMERIC(4,1) NOT NULL CHECK (relevant_experience_years >= 0),
  primary_skills      TEXT NOT NULL,
  certifications      TEXT,

  employment_status   employment_status NOT NULL,
  notice_period       VARCHAR(100),
  available_from      DATE NOT NULL,
  preferred_work_mode work_mode NOT NULL,
  willing_to_relocate BOOLEAN NOT NULL,

  current_ctc_lpa     NUMERIC(6,2) NOT NULL CHECK (current_ctc_lpa >= 0),
  expected_ctc_lpa    NUMERIC(6,2) NOT NULL CHECK (expected_ctc_lpa >= 0),

  interest_reason     TEXT NOT NULL,
  linkedin_portfolio_url VARCHAR(500),
  hear_about          hear_about_source NOT NULL,
  hear_about_other    VARCHAR(200),

  consent_given       BOOLEAN NOT NULL DEFAULT FALSE,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_relevant_lte_total
    CHECK (relevant_experience_years <= total_experience_years),
  CONSTRAINT chk_consent CHECK (consent_given = TRUE),
  CONSTRAINT chk_applied_role
    CHECK (
      (applied_role_id IS NOT NULL AND applied_role_other IS NULL)
      OR (applied_role_id IS NULL AND applied_role_other IS NOT NULL)
    ),
  CONSTRAINT chk_notice_when_employed
    CHECK (employment_status != 'employed' OR notice_period IS NOT NULL)
);

CREATE INDEX idx_candidate_forms_created_at ON candidate_forms (created_at DESC);
CREATE INDEX idx_candidate_forms_candidate_id ON candidate_forms (candidate_id);
CREATE INDEX idx_candidate_forms_email ON candidate_forms (email_address);
