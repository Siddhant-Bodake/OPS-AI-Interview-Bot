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
- skills: Look for skills in dedicated "Skills" sections (e.g., "Skills:", "Technical Skills:", etc.), within work experience descriptions, in project descriptions, or anywhere in the resume.
  Even if the resume is minimal, extract any technical terms, tools, or technologies mentioned.
- work_experience: company, role_title, start_date, end_date (or "Present"), description
- education: degree, institution, field_of_study, graduation_year
- projects: name, description, technologies
- certifications: name, issuer, date
- relevant_years_experience: your best estimate of the candidate's total years of experience that are RELEVANT to this specific role/domain (not just total years worked anywhere) — weigh work history and projects that align with the JD above.

Respond per the provided schema only."""


# ------------------------ SKILL MATCH --------------------------------------------
SKILL_MATCH_PROMPT = """You are matching a candidate's resume against a role's required skills, for the role of {role}.

Required skills (JD keywords): {jd_keywords}

Candidate's listed skills (name: years_experience):
{candidate_skills_block}

Candidate's certifications:
{candidate_certifications_block}

For EACH required skill, decide if the candidate demonstrates it — via a listed SKILL, via a relevant CERTIFICATION, or not at all. Include synonyms/abbreviations (e.g. "Go" matches "Golang", "K8s" matches "Kubernetes"). A certification counts as evidence when it's clearly about that technology (e.g. "AWS Certified Solutions Architect" -> "AWS"). Do not match unrelated skills just because they're in the same broad category.
For each required skill, respond with: jd_keyword, matched (bool), matched_via ("skill"/"certification"/"none"), matched_candidate_skill (the matching skill or certification name, or null), estimated_years (years_experience if matched via a skill, else 1.0 if matched via a certification, else 0).

Respond per the schema, one entry per required skill, in the same order given."""


# ------------------------ PROJECT RELEVANCE ----------------------------------------
PROJECT_RELEVANCE_PROMPT = """You are assessing how relevant a candidate's projects are to
the role of {role}. Job description context:

{jd_text}

Candidate's projects:
{projects_block}

Score 0-10 on how relevant and substantive these projects are to this specific role — consider both topical relevance (do they use similar tech/solve similar problems) and depth (is this a throwaway toy project or something with real scope). If the candidate listed no projects, score 0.

Respond with projects_score only, per the schema."""