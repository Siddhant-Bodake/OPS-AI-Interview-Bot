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

For each question, provide:
- "domain": "technical" or "behavioral"
- "text": the full interview question
- "source": "bank" or "generated"
- "title": a short label for the question topic (e.g. "REST API", "Database Transactions", "Team Collaboration")
- "follow_up": a follow-up question to probe deeper
- "difficulty": "easy", "medium", or "hard"
- "expected_concepts": a list of key concepts the candidate should cover in their answer
- "type": for technical questions use "core", "database", or "scenario_based"; for behavioral questions use "" (empty string)

Respond per the schema: a list of exactly {total_count} questions."""