GENERATION_PROMPT = """You are building an interview question set for the role of {role}.
Candidate seniority tier: {seniority_tier} (approx. {relevant_years} relevant years of experience).

Job description context: {jd_text}

Existing question bank for this role/tier (you may select from these as-is):
{bank_questions_block}

{type_distribution_hint}

{skill_match_hint}

Candidate's resume profile:
- Skills: {skills_block}
- Work experience: {experience_block}
- Projects: {projects_block}

EXACT COUNTS (non-negotiable):
- Total: {total_count} questions
- Technical: {technical_count}, Behavioral: {behavioral_count}
- Bank source: {bank_count}, Generated source: {generated_count}

CRITICAL RULES:
1. Each question must be DISTINCT in its core concept — no duplicates.
2. If you select a bank question, do NOT generate a new question on the same topic.
3. Technical questions MUST follow the type distribution exactly: core (40%), database (40%), scenario_based (20%).
4. Generated questions MUST reference something specific from the candidate's resume.

For each question, provide:
- "domain": "technical" or "behavioral"
- "text": the full interview question
- "source": "bank" or "generated"
- "title": a short label for the question topic
- "follow_up": a follow-up question to probe deeper
- "difficulty": "easy", "medium", or "hard"
- "expected_concepts": a list of key concepts
- "type": "core", "database", or "scenario_based" (technical only); "" for behavioral

Respond per the schema: a list of exactly {total_count} questions."""
