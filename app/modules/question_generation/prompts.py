GENERATION_PROMPT = """You are building an interview question set for the role of {role}.
Candidate seniority tier: {seniority_tier} (approx. {relevant_years} relevant years of experience).

Job description context: {jd_text}

Existing question bank for this role/tier (you may select from these as-is):
{bank_questions_block}

Candidate's resume profile:
- Skills: {skills_block}
- Work experience: {experience_block}
- Projects: {projects_block}

Build a set of exactly {total_count} interview questions:
- {technical_count} TECHNICAL questions, {behavioral_count} BEHAVIORAL questions
- Aim for roughly {bank_count} questions selected/adapted from the bank above (source="bank"),
  and roughly {generated_count} NEW questions written specifically from this candidate's resume
  (source="generated") — e.g. asking about a specific project, technology, or experience they listed.
- Bank questions should be used verbatim or lightly adapted, not rewritten beyond recognition.
- Generated questions must reference something concrete and specific to THIS resume — not generic.
- Do not repeat the same underlying question twice.

Respond per the schema: a list of exactly {total_count} questions, each with domain, text, and source."""