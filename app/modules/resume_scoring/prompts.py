"""Prompt for LLM-based resume extraction (Module 2)."""


# ------------------------ EXTRACTION -------------------------------------------
EXTRACTION_PROMPT = """You are extracting structured information from a candidate's resume
for the role of {role}. Job description context:

{jd_text}

Resume text (raw, may have OCR/formatting artifacts):
---
{resume_text}
---

Extract:
- candidate_name
- summary: professional summary/objective if present
- skills: Resumes often group skills under category subheadings followed by a comma-separated
  list, e.g. "Backend: Spring Boot, Spring MVC, Redis, Kafka" or "Languages: Java, JavaScript, SQL".
  When you see this pattern: extract EACH comma-separated item as its own individual skill
  entry. Do NOT treat the category label itself (e.g. "Backend", "Frontend", "DevOps") as a
  skill. Do NOT merge multiple items into one entry, and do NOT drop items partway through a
  long list — go through the full list item by item. If no explicit years are stated for a
  skill (common in a flat skills list like this), set years_experience to 0 rather than
  guessing a number.
- work_experience: company, role_title, start_date, end_date (or "Present"), description
- education: degree, institution, field_of_study, graduation_year
- projects: name, description, technologies
- certifications: name, issuer, date
- relevant_years_experience: your best estimate of the candidate's total years of experience
  RELEVANT to this specific role/domain — weigh work history and projects that align with the
  JD above.

Respond per the provided schema only."""


# ------------------------ SCORING -------------------------------------------
SCORING_PROMPT = """You are evaluating a candidate's resume against the role of {role}.
This role typically expects around {expected_years} years of relevant experience — use this only as calibration context, not a hard cutoff.

Job description context: {jd_text}

--- Extracted resume data ---
Summary: {summary_block}
Skills: {skills_block}
Certifications: {certifications_block}
Projects: {projects_block}
Work experience: {experience_block}
Other sections (Languages, Awards, Publications, Volunteer, etc.): {other_sections_block}
---

TASK 1 — Summary relevance:
Judge how relevant the candidate's summary/objective is to this role's JD, 0-100%.
If no summary is present, respond 0.

TASK 2 — Skills + certifications matching:
Core skills for this role (languages/frameworks/architecture — the primary evaluation criteria): {core_keywords}
Supporting skills (tooling/infrastructure — secondary, matters less at senior levels): {supporting_keywords}

For EACH skill in both lists, decide if the candidate demonstrates it via a listed SKILL, a relevant CERTIFICATION (not necessary for every skill, atleast for any 2 core skills), or not at all. Include synonyms/abbreviations (e.g. "Go" matches "Golang", "K8s" matches "Kubernetes"). Respond per skill: jd_keyword, matched, matched_via, matched_candidate_skill, estimated_years.

TASK 3 — Project relevance:
For EACH listed project, judge relevance to this role's JD, 0-100% — consider both topical fit and depth (real scope vs. a toy project).

TASK 4 — Experience relevance:
Judge how relevant the candidate's overall work experience is to this role's JD, 0-100% — consider both the type of work and its depth, not just years.

TASK 5 — Other (bonus, be conservative):
If content in "other sections" is genuinely valuable for this specific role (e.g. a directly relevant published paper, a role-relevant language requirement met, a notable award), award 0 to 0.5. Most resumes should score 0 or close to it here — this is a minor bonus, not a major scoring dimension.

Respond per the schema."""