GENERATION_PROMPT = """You are building an interview question set for the role of {role}.
Candidate seniority tier: {seniority_tier} (approx. {relevant_years} relevant years of experience).

Job description context: {jd_text}

REFERENCE question bank (use ONLY if a question is highly relevant to this specific candidate's skills/projects):
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
- Bank source: {bank_count} (ONLY if highly relevant to candidate)
- Generated source: {generated_count} (PREFERRED — tailored to candidate's resume)

FILTERING RULE FOR BANK QUESTIONS:
- Only select a bank question if it directly relates to the candidate's listed skills or projects
- Skip generic questions (e.g., "What is a REST API?") unless the candidate's resume suggests they need to demonstrate that knowledge
- Prefer GENERATED questions that reference the candidate's actual work experience

CRITICAL RULES:
1. Each question must be DISTINCT in its core concept — no duplicates.
2. If you select a bank question, do NOT generate a new question on the same topic.
3. Technical questions MUST follow the type distribution exactly: core (40%), database (40%), scenario_based (20%).
4. PRIORITY: Generate questions that ask about the candidate's SPECIFIC projects, technologies, and experiences.
5. Each generated question should be impossible to answer without knowing THIS candidate's resume.

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
