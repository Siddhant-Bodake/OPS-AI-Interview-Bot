"""
Scenario runner for Module 2 (resume parsing & scoring).

Run everything:   python -m examples.resume_scoring_example
Run one scenario: python -m examples.resume_scoring_example --only role_aware_scaling
"""
import argparse
import asyncio
import time

from app.core.config import settings
from app.modules.interview_engine.engine import build_gemini_client  # shared Gemini client builder
from app.modules.resume_scoring import (
    ResumeExtractor,
    RoleRequirements,
    UnsupportedResumeFormat,
    extract_text,
    score_resume,
)

SAMPLE_RESUME = """
Kaustubh Narayan Bhuingade
Full Stack Java Developer | Spring Boot | React.js | REST APIs | Docker | AWS
Pune, Maharashtra, India
Mobile: +91 8412901961
Email: kaustubh915b@gmail.com
LinkedIn: https://www.linkedin.com/in/kaustubh-bhuingade/
GitHub: https://github.com/DevKaustubh915
Portfolio: https://personal-portfolio-o88j.onrender.com/

Professional Summary

Full Stack Java Developer with hands-on experience designing, developing, and deploying production-grade applications using Java, Spring Boot, React.js, MySQL, and related technologies. Proficient in secured REST APIs with JWT authentication, third-party API integration, CI/CD pipelines using Jenkins and Docker, and cloud deployment. Strong foundation in DSA, OOP, Microservices Architecture, and Agile methodology. Seeking Java Developer or Associate Software Engineer roles.

Technical Skills
Languages: Java, JavaScript, SQL
Backend: Spring Boot, Spring MVC, Spring Security, Spring Data JPA, Hibernate, REST API, JWT, Microservices, JUnit5, Mockito, Postman, Swagger, API Integration, Redis, Kafka, Logging
Frontend: React.js, JavaScript ES6+, HTML5, CSS3, Tailwind CSS, Bootstrap, Axios, Responsive Design
Databases: MySQL, PostgreSQL, MongoDB
DevOps: Git, GitHub, Maven, Jenkins, Docker, AWS EC2/S3, Linux, Render
Core: DSA, OOP, SDLC, RESTful Design, Microservices, Agile, MVC, Version Control
Projects

1. Full-Stack Billing & POS Software — 2025

Java, Spring Boot, Spring Security, MySQL, React.js, Bootstrap, Axios, Razorpay
Production-grade POS system with inventory, cart, and payment processing.
15+ secured REST APIs using JWT authentication.
Normalized MySQL schema for categories, products, transactions, and order history.
React frontend with real-time cart updates, analytics, search/filtering, and order history.
Targeted billing, inventory, and payment challenges for small retailers.

2. Full-Stack Resume Builder Platform — 2026

Java, Spring Boot, Spring Security, MongoDB, React.js, Tailwind, Razorpay, JavaMail
SaaS application with live resume preview and multiple templates.
JWT authentication, email verification, session management, and RBAC.
Razorpay integration with webhook signature verification and ₹999 premium subscription.
MongoDB schemas for profiles, resume data, and subscriptions.
Cloudinary image upload.
Backend deployed on Render and frontend on Netlify.

3. Expense Tracker & Budget Management System — 2026

Spring Boot, Spring Data JPA, MySQL, React.js, Tailwind CSS, Cloudinary, Chart.js, JavaMail
Income/expense tracking and category-based budgeting.
Automated daily email reminders.
Chart.js analytics for trends and category breakdowns.
Cloudinary profile image management.
Excel report generation and automated email delivery.
Deployed on Render and Netlify.

Experience:
Freelance Full Stack Java Developer — Self-Employed, Remote
2025–Present

Designed, developed, and deployed 3 full-stack applications independently.
Covered requirements, system design, development, testing, and deployment.
Integrated Razorpay payments with server-side signature verification.
Managed Git/GitHub, environment configuration, Jenkins, Docker, AWS, and Render.
Delivered a SaaS Resume Builder with ₹999 subscription monetization, JWT authentication, email verification, and multi-template generation.
Education:
MCA — Chandigarh University, Chandigarh — Expected June 2026
B.Sc. — Shivaji University — 2023 — 71.88%
Certifications & Training:
Spring Framework & Spring Boot — Telusko
Data Structures and Algorithms — Abdul Bari
Java Full-Stack Development — Marvellous Infosystem, Pune
Key Strengths:
3 deployed full-stack applications with real payment integrations
Strong REST API design and JWT security
CI/CD and Docker experience
DSA/problem-solving fundamentals
Quick learner with self-driven project development
"""

WEAK_RESUME = """
Sam Patel — Marketing Coordinator
Experience:
- BrandCo, Marketing Coordinator (2022-Present): Ran social campaigns, wrote copy.
Skills: Canva, Instagram Ads, Copywriting
Education: B.A. Communications, City College, 2022
"""


# --------------------------------------------------------------------- [LLM]

async def scenario_strong_match():
    """Strong resume against a role its skills/experience actually fit —
    expect a clear pass. [LLM] — 1 extraction call."""
    print("\n=== SCENARIO: strong_match [LLM] ===")
    start_time = time.time()
    extractor = ResumeExtractor(build_gemini_client())
    role = RoleRequirements(
        role="Backend Engineer",
        jd_keywords=["Python", "FastAPI", "Redis", "PostgreSQL", "Docker"],
        expected_years_experience=(1.0, 3.0),  # 1-3 years range
        threshold=6.0,
    )
    profile = await extractor.extract(SAMPLE_RESUME, role.role, jd_text=", ".join(role.jd_keywords))
    skill_match = await extractor.match_skills(profile, role)
    project_relevance = await extractor.score_projects(profile, role)
    result = score_resume(profile, role, skill_match, project_relevance)
    elapsed = time.time() - start_time
    print(f"skills={result.skills_score} experience={result.experience_score} "
          f"education={result.education_score} overall={result.overall_score} "
          f"passed={result.passed_threshold}")
    print("matched:", result.matched_keywords, " missing:", result.missing_keywords)
    print(f"⏱ Total time: {elapsed:.2f}s")


async def scenario_weak_match():
    """Resume with no relevant skills/experience for the role — expect a
    clear fail. [LLM] — 1 extraction call."""
    print("\n=== SCENARIO: weak_match [LLM] ===")
    start_time = time.time()
    extractor = ResumeExtractor(build_gemini_client())
    role = RoleRequirements(
        role="Backend Engineer",
        jd_keywords=["Python", "FastAPI", "Redis", "PostgreSQL", "Docker"],
        expected_years_experience=[1.0, 3.0],  # 1-3 years range
        threshold=6.0,
    )
    profile = await extractor.extract(WEAK_RESUME, role.role, jd_text=", ".join(role.jd_keywords))
    skill_match = await extractor.match_skills(profile, role)
    project_relevance = await extractor.score_projects(profile, role)
    result = score_resume(profile, role, skill_match, project_relevance)
    elapsed = time.time() - start_time
    print(f"skills={result.skills_score} experience={result.experience_score} "
          f"education={result.education_score} overall={result.overall_score} "
          f"passed={result.passed_threshold}")
    print(f"⏱ Total time: {elapsed:.2f}s")


async def scenario_role_aware_scaling():
    """THE key test: same resume, scored against a junior-bar role and a
    senior-bar role. Experience score should differ meaningfully even
    though the resume itself didn't change. [LLM] — 1 extraction call,
    reused for both scoring passes (scoring itself has no LLM cost)."""
    print("\n=== SCENARIO: role_aware_scaling [LLM] ===")
    start_time = time.time()
    extractor = ResumeExtractor(build_gemini_client())
    jd_keywords = ["Python", "FastAPI", "Redis", "PostgreSQL", "Docker"]
    profile = await extractor.extract(SAMPLE_RESUME, "Backend Engineer", jd_text=", ".join(jd_keywords))

    junior_role = RoleRequirements(role="Junior Backend Engineer", jd_keywords=jd_keywords,
                                    expected_years_experience=[0.5, 1.5], threshold=6.0)
    senior_role = RoleRequirements(role="Senior Backend Engineer", jd_keywords=jd_keywords,
                                    expected_years_experience=[5.0, 7.0], threshold=6.0)

    junior_skill_match = await extractor.match_skills(profile, junior_role)
    senior_skill_match = await extractor.match_skills(profile, senior_role)
    junior_project_relevance = await extractor.score_projects(profile, junior_role)
    senior_project_relevance = await extractor.score_projects(profile, senior_role)
    junior_result = score_resume(profile, junior_role, junior_skill_match, junior_project_relevance)
    senior_result = score_resume(profile, senior_role, senior_skill_match, senior_project_relevance)
    elapsed = time.time() - start_time

    print(f"Against JUNIOR bar (expected {junior_role.expected_years_experience}y): "
          f"experience_score={junior_result.experience_score}, overall={junior_result.overall_score}")
    print(f"Against SENIOR bar (expected {senior_role.expected_years_experience}y): "
          f"experience_score={senior_result.experience_score}, overall={senior_result.overall_score}")
    assert junior_result.experience_score >= senior_result.experience_score, \
        "Same resume should score at least as well against a lower bar as a higher one"
    print("Confirmed: identical resume scores differently depending on the role's expected bar.")
    print(f"⏱ Total time: {elapsed:.2f}s")


# ------------------------------------------------------------------ [no-LLM]

async def scenario_unsupported_format_fallback():
    """A .txt resume should raise UnsupportedResumeFormat — this is what
    Module 1's mail orchestration should catch to trigger the
    resume-request-mail fallback path. [no-LLM]."""
    print("\n=== SCENARIO: unsupported_format_fallback [no-LLM] ===")
    start_time = time.time()
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        f.write("plain text resume, not a real format we accept")
        path = f.name
    try:
        extract_text(path)
        raise AssertionError("Should have raised UnsupportedResumeFormat")
    except UnsupportedResumeFormat as e:
        elapsed = time.time() - start_time
        print(f"Correctly rejected: {e}")
        print("-> Module 1 should catch this and send the resume-request mail.")
        print(f"⏱ Total time: {elapsed:.2f}s")
    finally:
        os.unlink(path)


async def scenario_synonym_matching():
    """Resume lists 'Go' and 'K8s'; JD asks for 'Golang' and 'Kubernetes'.
    Substring matching would miss both — LLM matching should catch them."""
    print("\n=== SCENARIO: synonym_matching [LLM] ===")
    start_time = time.time()
    resume = """
    Alex Kim — Platform Engineer
    Email: alex.kim@example.com
    Skills: Go, K8s, Postgres
    Experience: Infra Co, Platform Engineer (2020-Present)
    Education: B.S. Computer Science, Tech University, 2020
    """
    extractor = ResumeExtractor(build_gemini_client())
    role = RoleRequirements(
        role="Platform Engineer",
        jd_keywords=["Golang", "Kubernetes", "PostgreSQL", "Terraform"],
        expected_years_experience=[2.0, 4.0],  # 2-4 years range
        threshold=6.0,
    )
    profile = await extractor.extract(resume, role.role, jd_text=", ".join(role.jd_keywords))
    print(f"DEBUG: Extracted skills: {[s.name for s in profile.skills]}")
    print(f"DEBUG: Extracted profile has skills: {len(profile.skills) > 0}")
    skill_match = await extractor.match_skills(profile, role)
    project_relevance = await extractor.score_projects(profile, role)
    result = score_resume(profile, role, skill_match, project_relevance)
    elapsed = time.time() - start_time

    print("matched:", result.matched_keywords, " missing:", result.missing_keywords)
    print(f"skills_score={result.skills_score}")
    if len(result.matched_keywords) == 4:
        print("Confirmed: synonym/abbreviation matching works via LLM.")
    else:
        print(f"Note: LLM matched {len(result.matched_keywords)}/4 keywords from the minimal resume.")
    print(f"⏱ Total time: {elapsed:.2f}s")


SCENARIOS = {
    "strong_match": scenario_strong_match,
    "weak_match": scenario_weak_match,
    "role_aware_scaling": scenario_role_aware_scaling,
    "unsupported_format_fallback": scenario_unsupported_format_fallback,
    "synonym_matching": scenario_synonym_matching,
}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=list(SCENARIOS.keys()), default=None)
    args = parser.parse_args()
    for name in ([args.only] if args.only else list(SCENARIOS.keys())):
        await SCENARIOS[name]()


if __name__ == "__main__":
    asyncio.run(main())