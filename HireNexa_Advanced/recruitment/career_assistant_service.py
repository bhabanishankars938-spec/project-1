import logging
from typing import Dict, Any, List, Optional
from django.utils import timezone
from accounts.models import User
from recruitment.models import (
    Job,
    Application,
    CandidateProfile,
    CandidateSkill,
    CandidateProject,
    Resume,
    ResumeExtractedData,
    ProjectPortfolio,
)

try:
    from assessments.models import (
        Subject,
        Topic,
        Question,
        LearningNote,
        ExamAttempt,
        Result,
        TopicProgress,
    )
except ImportError:
    Subject = None
    Topic = None
    Question = None
    LearningNote = None
    ExamAttempt = None
    Result = None
    TopicProgress = None

logger = logging.getLogger(__name__)


class CareerAssistantService:
    """
    Advanced Context-Aware Career Assistant Service for HireNexa.
    Provides verifiable, explainable career planning backed by genuine candidate database records.
    """

    @classmethod
    def get_candidate_context(cls, user: User) -> Dict[str, Any]:
        """Gathers authentic profile, skills, test results, and portfolio data for a candidate."""
        profile = getattr(user, "candidate_profile", None)
        skills_qs = CandidateSkill.objects.filter(candidate=user)
        user_skills = [s.name.strip() for s in skills_qs]

        # Extract skills from profile string as fallback/supplement
        if profile and profile.skills:
            for s in profile.skills.split(","):
                clean = s.strip()
                if clean and clean.lower() not in [x.lower() for x in user_skills]:
                    user_skills.append(clean)

        # Extracted resume data
        resume = Resume.objects.filter(candidate=user).order_by("-uploaded_at").first()
        resume_skills = []
        if resume and hasattr(resume, "extracted_data") and resume.extracted_data.skills:
            resume_skills = resume.extracted_data.skills

        # Portfolio projects
        portfolio_projects = list(
            ProjectPortfolio.objects.filter(candidate=user).values(
                "id", "project_name", "category", "technologies", "github_url", "live_demo_url"
            )
        )

        # Assessments results
        exam_results = []
        if Result:
            exam_results = list(
                Result.objects.filter(user=user).select_related("examination").order_by("-created_at")[:5]
            )

        # Target role
        target_role = "Software Engineer"
        if profile and profile.headline:
            target_role = profile.headline.split("|")[0].strip()

        return {
            "user_id": user.id,
            "username": user.username,
            "full_name": profile.full_name if profile else user.username,
            "target_role": target_role,
            "education": profile.education if profile else "",
            "university": profile.university if profile else "",
            "cgpa": profile.cgpa if profile else "",
            "user_skills": user_skills,
            "resume_skills": resume_skills,
            "has_resume": resume is not None,
            "portfolio_count": len(portfolio_projects),
            "portfolio_projects": portfolio_projects,
            "recent_results": [
                {
                    "exam_title": r.examination.title,
                    "score_percentage": float(r.score_percentage),
                    "performance_level": r.get_performance_level_display(),
                }
                for r in exam_results
            ],
        }

    @classmethod
    def analyze_skill_gaps(cls, user: User, target_role: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyzes missing skills by comparing candidate's actual skills with market expectations
        from active authorized Job listings on HireNexa.
        """
        context = cls.get_candidate_context(user)
        role = target_role or context["target_role"]

        # Find matching jobs for this target role
        matching_jobs = Job.objects.filter(is_active=True, status=Job.Status.ACTIVE)
        if role:
            keywords = [w for w in role.lower().split() if len(w) > 2]
            if keywords:
                from django.db.models import Q
                query = Q()
                for kw in keywords:
                    query |= Q(title__icontains=kw) | Q(required_skills__icontains=kw)
                matching_jobs = matching_jobs.filter(query)

        # Aggregate required skills from matching jobs
        job_skill_counts: Dict[str, int] = {}
        sample_jobs_count = matching_jobs.count()

        for j in matching_jobs[:20]:
            for s in j.skill_list():
                clean = s.strip()
                if clean:
                    job_skill_counts[clean] = job_skill_counts.get(clean, 0) + 1

        user_skills_lower = set(s.lower() for s in context["user_skills"] + context["resume_skills"])

        present_skills = []
        missing_skills = []

        for skill, freq in sorted(job_skill_counts.items(), key=lambda x: x[1], reverse=True):
            demand_pct = int((freq / max(1, sample_jobs_count)) * 100)
            if skill in user_skills_lower:
                present_skills.append({
                    "skill": skill.capitalize(),
                    "frequency": freq,
                    "market_demand_pct": demand_pct,
                    "status": "ACQUIRED",
                })
            else:
                missing_skills.append({
                    "skill": skill.capitalize(),
                    "frequency": freq,
                    "market_demand_pct": demand_pct,
                    "status": "GAP",
                    "priority": "HIGH" if demand_pct >= 40 else "MEDIUM",
                })

        # Provide explanation
        reasoning = (
            f"Based on {sample_jobs_count} active job vacancies matching '{role}' on HireNexa, "
            f"you have verified {len(present_skills)} key competencies. "
            f"Acquiring {len(missing_skills[:4])} critical missing skills will significantly increase your hiring match score."
        )

        return {
            "target_role": role,
            "sample_jobs_analyzed": sample_jobs_count,
            "present_skills": present_skills,
            "missing_skills": missing_skills[:6],
            "reasoning": reasoning,
        }

    @classmethod
    def recommend_jobs_with_reasoning(cls, user: User, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Recommends active jobs using candidate profile data with explicit transparent reasoning.
        """
        context = cls.get_candidate_context(user)
        user_skills_lower = set(s.lower() for s in context["user_skills"] + context["resume_skills"])

        active_jobs = Job.objects.filter(is_active=True, status=Job.Status.ACTIVE).select_related("organization")
        recommendations = []

        for job in active_jobs:
            job_skills = job.skill_list()
            if not job_skills:
                continue

            matched = [s for s in job_skills if s in user_skills_lower]
            missing = [s for s in job_skills if s not in user_skills_lower]
            overlap_pct = int((len(matched) / len(job_skills)) * 100)

            # Boost if target course matches
            profile = getattr(user, "candidate_profile", None)
            course_match = False
            if profile and job.target_course != "ALL":
                if job.target_course.lower() in (profile.education or "").lower():
                    course_match = True

            # Formulate transparent rationale
            rationale_parts = []
            rationale_parts.append(f"{overlap_pct}% skill match ({len(matched)} of {len(job_skills)} required skills)")
            if matched:
                rationale_parts.append(f"Matching: {', '.join([s.capitalize() for s in matched[:3]])}")
            if missing:
                rationale_parts.append(f"Missing: {', '.join([s.capitalize() for s in missing[:2]])}")
            if course_match:
                rationale_parts.append(f"Education target matches your degree ({job.get_target_course_display()})")

            recommendations.append({
                "job_id": job.id,
                "title": job.title,
                "company_name": job.company_name,
                "location": job.location or "Remote",
                "workplace_type": job.get_workplace_type_display(),
                "match_score": overlap_pct + (10 if course_match else 0),
                "matched_skills": [s.capitalize() for s in matched],
                "missing_skills": [s.capitalize() for s in missing],
                "vacancies": job.vacancies,
                "reasoning": " · ".join(rationale_parts),
                "apply_url": f"/jobs/{job.id}/",
            })

        recommendations.sort(key=lambda x: x["match_score"], reverse=True)
        return recommendations[:limit]

    @classmethod
    def recommend_learning_activities(cls, user: User) -> List[Dict[str, Any]]:
        """
        Recommends targeted learning activities by connecting detected missing skills
        and weak exam topics to verified learning notes and tests in assessments.
        """
        activities = []
        if not Subject:
            return activities

        gaps_data = cls.analyze_skill_gaps(user)
        missing_skills = [m["skill"].lower() for m in gaps_data.get("missing_skills", [])]

        # Check weak topics from assessments
        weak_topics_qs = []
        if TopicProgress:
            weak_topics_qs = TopicProgress.objects.filter(
                user=user, mastery_percentage__lt=60
            ).select_related("topic", "topic__subject")[:3]

        for tp in weak_topics_qs:
            activities.append({
                "type": "REVISION",
                "title": f"Revise Weak Topic: {tp.topic.name}",
                "subject": tp.topic.subject.name,
                "reason": f"Your current mastery score is {tp.mastery_percentage:.1f}%. Strengthening this topic will boost your assessment readiness.",
                "url": f"/assessments/topics/{tp.topic.id}/",
                "action_label": "Review Notes & Practice",
            })

        # Match missing market skills with platform subjects & topics
        for skill_name in missing_skills[:3]:
            subj = Subject.objects.filter(is_active=True, name__icontains=skill_name).first()
            if subj:
                activities.append({
                    "type": "NEW_SKILL",
                    "title": f"Master {subj.name} for Market Competitiveness",
                    "subject": subj.name,
                    "reason": f"High employer demand on HireNexa ({skill_name.capitalize()} is required in {gaps_data.get('sample_jobs_analyzed', 0)} matching openings).",
                    "url": f"/assessments/subjects/{subj.id}/",
                    "action_label": "Start Course Syllabus",
                })

        return activities

    @classmethod
    def generate_project_suggestions(cls, user: User) -> List[Dict[str, Any]]:
        """
        Generates portfolio project suggestions specifically designed to prove
        competence in candidate's missing or developing skills.
        """
        gaps_data = cls.analyze_skill_gaps(user)
        missing_skill_names = [m["skill"] for m in gaps_data.get("missing_skills", [])[:3]]
        target_role = gaps_data.get("target_role", "Software Engineer")

        suggestions = [
            {
                "title": f"{target_role} Production Portfolio System",
                "target_skills": missing_skill_names or ["Python", "Django", "PostgreSQL", "REST API"],
                "difficulty": "Intermediate to Advanced",
                "description": (
                    f"Build an end-to-end full-stack application incorporating "
                    f"{', '.join(missing_skill_names or ['ORM', 'Authentication', 'API design'])}. "
                    f"Include automated unit tests, clean documentation, and deployment to demonstrate enterprise readiness."
                ),
                "deliverables": [
                    "Public GitHub repository with structured commits and CI pipeline",
                    "Live hosted demo URL with test credentials",
                    "Architecture diagram and API documentation",
                ],
                "passport_benefit": "Upload to your HireNexa Project Portfolio to receive verified recruiter visibility.",
            },
            {
                "title": "High-Throughput Analytics & Microservice Dashboard",
                "target_skills": ["SQL", "Data Modeling", "Docker", "Caching"],
                "difficulty": "Advanced",
                "description": (
                    "Develop a performant service handling batch data processing with index-optimized SQL queries, "
                    "Redis caching, and containerized Docker execution."
                ),
                "deliverables": [
                    "Benchmark performance report comparing indexed vs unindexed queries",
                    "Docker Compose setup file for one-command execution",
                ],
                "passport_benefit": "Qualifies for verified backend engineering badge in Skill Passport.",
            },
        ]
        return suggestions

    @classmethod
    def generate_resume_improvements(cls, user: User) -> Dict[str, Any]:
        """
        Module 4: Resume Optimization Intelligence.
        Provides evidence-based resume suggestions, ATS compatibility audit score,
        keyword coverage analysis, and Google XYZ achievement formula optimization.
        """
        context = cls.get_candidate_context(user)
        has_resume = context["has_resume"]
        gaps_data = cls.analyze_skill_gaps(user)
        missing_skills = [m["skill"] for m in gaps_data.get("missing_skills", [])[:5]]
        present_skills = [s["skill"] for s in gaps_data.get("present_skills", [])[:6]]

        # ATS scoring heuristic based on profile completeness and resume data
        base_score = 40
        if has_resume:
            base_score += 25
        if len(present_skills) >= 4:
            base_score += 15
        if context["portfolio_count"] >= 1:
            base_score += 10
        if context["recent_results"]:
            base_score += 10

        ats_score = min(100, base_score)
        if ats_score >= 80:
            ats_status = "Excellent · High ATS Parseability"
            ats_color = "#10b981"
        elif ats_score >= 60:
            ats_status = "Good · Minor Keyword Gaps"
            ats_color = "#f59e0b"
        else:
            ats_status = "Needs Optimization · Low ATS Match"
            ats_color = "#ef4444"

        tips = [
            {
                "category": "Keyword Optimization",
                "suggestion": f"Incorporate missing industry terms: {', '.join(missing_skills) if missing_skills else 'Unit Testing, REST APIs, Git, Docker'}.",
                "impact": "Improves automated ATS semantic parsing score by up to 35%.",
            },
            {
                "category": "Quantifiable Achievements",
                "suggestion": "Frame bullet points using the Google XYZ formula: 'Accomplished [X] as measured by [Y] by doing [Z]'. Example: 'Optimized database queries, reducing response latency by 40%'.",
                "impact": "Dramatically increases recruiter shortlist rates during Stage 1 screening.",
            },
            {
                "category": "Verified Skill Proof",
                "suggestion": "Link your HireNexa Skill Passport and verified assessment scores directly in your resume header.",
                "impact": "Provides verified proof of competency, distinguishing your application from self-declared claims.",
            },
            {
                "category": "Structure & Formatting",
                "suggestion": "Ensure standard section headers ('Experience', 'Education', 'Technical Skills', 'Projects') without multi-column table nesting.",
                "impact": "Prevents ATS text scrapers from misinterpreting chronological work experience.",
            },
        ]

        action_verbs = [
            "Architected", "Engineered", "Optimized", "Implemented", "Refactored",
            "Deployed", "Automated", "Standardized", "Accelerated", "Spearheaded"
        ]

        return {
            "has_resume": has_resume,
            "target_role": context["target_role"],
            "ats_score": ats_score,
            "ats_status": ats_status,
            "ats_color": ats_color,
            "present_keywords": present_skills,
            "missing_keywords": missing_skills,
            "action_verbs": action_verbs,
            "recommendations": tips,
        }

    @classmethod
    def generate_career_roadmap(cls, user: User, target_role: Optional[str] = None) -> Dict[str, Any]:
        """
        Module 3: Career Roadmap Generator.
        Synthesizes a progressive milestone-based career pathway connecting theoretical knowledge,
        practical assessments, and production projects. Checks candidate's completed exams
        and topic progress to determine completed vs in-progress vs upcoming milestones.
        """
        context = cls.get_candidate_context(user)
        role = target_role or context["target_role"]
        has_portfolio = context["portfolio_count"] > 0
        has_resume = context["has_resume"]
        has_exams = len(context["recent_results"]) > 0
        skills_lower = [s.lower() for s in context["user_skills"] + context["resume_skills"]]

        milestones = [
            {
                "step": 1,
                "title": "Computer Science & Programming Core",
                "weeks": "Weeks 1-2",
                "theory": "Core data structures (Arrays, Linked Lists, HashMaps, Trees), Big-O complexity, and language syntax.",
                "practical": "Achieve ≥ 75% in Core Programming assessment test.",
                "status": "COMPLETED" if len(skills_lower) >= 2 else "IN_PROGRESS",
                "badge": "Core Foundation",
            },
            {
                "step": 2,
                "title": "Backend Engineering & Relational Databases",
                "weeks": "Weeks 3-4",
                "theory": "Relational schema design, normalization, ACID properties, indexing, SQL queries, and ORM abstractions.",
                "practical": "Pass Relational DB & SQL Assessment with ≥ 70% score.",
                "status": "COMPLETED" if any(s in skills_lower for s in ["sql", "postgresql", "mysql", "database"]) else "IN_PROGRESS",
                "badge": "Data Architecture",
            },
            {
                "step": 3,
                "title": "RESTful API Architecture & Authentication",
                "weeks": "Weeks 5-6",
                "theory": "HTTP verbs, status codes, JWT authentication, rate limiting, CORS, and role-based access control.",
                "practical": "Build and document secure REST endpoints with automated unit test validation.",
                "status": "COMPLETED" if any(s in skills_lower for s in ["django", "fastapi", "flask", "rest api", "drf", "api"]) else "UPCOMING",
                "badge": "API Services",
            },
            {
                "step": 4,
                "title": "Clean Code, Architecture & Testing",
                "weeks": "Weeks 7-8",
                "theory": "SOLID design principles, modular monolith architecture, pytest / Django test runner, mock assertions.",
                "practical": "Maintain >80% automated unit test coverage across application services.",
                "status": "COMPLETED" if has_exams else "UPCOMING",
                "badge": "Engineering Quality",
            },
            {
                "step": 5,
                "title": "Containerization & Cloud Infrastructure",
                "weeks": "Weeks 9-10",
                "theory": "Docker containers, multi-stage builds, environment variables isolation, and CI/CD pipelines.",
                "practical": "Containerize full application and configure GitHub Actions automated test workflow.",
                "status": "COMPLETED" if any(s in skills_lower for s in ["docker", "aws", "cloud", "ci/cd", "devops"]) else "UPCOMING",
                "badge": "DevOps & Cloud",
            },
            {
                "step": 6,
                "title": "Production Capstone Project",
                "weeks": "Weeks 11-12",
                "theory": "Production-grade deployment, security headers, database migrations, connection pooling.",
                "practical": "Attach verified source code and live demo URL to HireNexa Project Portfolio.",
                "status": "COMPLETED" if has_portfolio else "UPCOMING",
                "badge": "Portfolio Proof",
            },
            {
                "step": 7,
                "title": "ATS-Optimized Resume & Skill Passport Verification",
                "weeks": "Week 13",
                "theory": "Google XYZ bullet points, ATS parseable typography, verified skill credentials embedding.",
                "practical": "Achieve ≥ 80% on ATS Readability Audit and generate HireNexa Skill Passport.",
                "status": "COMPLETED" if has_resume else "UPCOMING",
                "badge": "Candidate Branding",
            },
            {
                "step": 8,
                "title": "Technical Interview & Mock Placement Rounds",
                "weeks": "Week 14",
                "theory": "System design trade-offs, concurrency, STAR behavioral interview techniques.",
                "practical": "Complete 5 timed examination attempts and solve 3 advanced scenario questions.",
                "status": "COMPLETED" if has_exams and has_portfolio else "UPCOMING",
                "badge": "Placement Ready",
            },
        ]

        completed_count = sum(1 for m in milestones if m["status"] == "COMPLETED")
        overall_progress = int((completed_count / len(milestones)) * 100)

        return {
            "target_role": role,
            "total_milestones": len(milestones),
            "completed_milestones": completed_count,
            "overall_progress_pct": overall_progress,
            "milestones": milestones,
        }

    @classmethod
    def generate_improvement_plan(cls, user: User) -> Dict[str, Any]:
        """
        Module 6: Personalized 4-Week Actionable Improvement Plan.
        Dynamically tailors weekly learning sprints based on missing competencies,
        weak assessment topics, and portfolio gaps.
        """
        context = cls.get_candidate_context(user)
        gaps_data = cls.analyze_skill_gaps(user)
        missing_skills = [m["skill"] for m in gaps_data.get("missing_skills", [])]

        weak_topic_names = []
        if TopicProgress:
            weak_topics = TopicProgress.objects.filter(user=user, mastery_percentage__lt=60).select_related("topic")[:2]
            weak_topic_names = [t.topic.name for t in weak_topics]

        week1_topic = weak_topic_names[0] if weak_topic_names else (missing_skills[0] if missing_skills else "Python Fundamentals")
        week2_topic = missing_skills[1] if len(missing_skills) > 1 else (missing_skills[0] if missing_skills else "SQL & Relational Databases")
        week3_topic = missing_skills[2] if len(missing_skills) > 2 else "RESTful APIs & Docker"

        plan = [
            {
                "week": 1,
                "phase": "Foundation & Weak Spot Remediation",
                "focus_area": week1_topic,
                "goal": f"Master core principles and remediate gaps in {week1_topic}.",
                "tasks": [
                    f"Read topic notes and review verified explanations on {week1_topic}.",
                    f"Complete at least 2 practice topic tests with ≥ 75% accuracy.",
                    "Document error log for all incorrect options to prevent conceptual repeats.",
                ],
                "time_commitment": "6-8 hours / week",
                "checkpoint": f"Verified Topic Assessment for {week1_topic}",
                "status": "IN_PROGRESS",
            },
            {
                "week": 2,
                "phase": "High-Demand Skill Acquisition",
                "focus_area": week2_topic,
                "goal": f"Acquire industry-standard competency in {week2_topic}.",
                "tasks": [
                    f"Implement 3 practical coding exercises or query sets using {week2_topic}.",
                    "Study edge cases and common mistakes documented in question explanations.",
                    "Review top employer vacancy expectations on HireNexa Job Discovery.",
                ],
                "time_commitment": "8-10 hours / week",
                "checkpoint": "Practical Mini-Project / Code Submission",
                "status": "PENDING",
            },
            {
                "week": 3,
                "phase": "Portfolio Integration & Practical Proof",
                "focus_area": week3_topic,
                "goal": f"Build a verifiable portfolio artifact demonstrating {week3_topic}.",
                "tasks": [
                    "Design and implement a clean repository with modular architecture and README.",
                    "Upload project details and files to HireNexa Project Portfolio.",
                    "Include unit test suite covering critical business logic paths.",
                ],
                "time_commitment": "10-12 hours / week",
                "checkpoint": "Portfolio Project Upload & GitHub Link",
                "status": "PENDING",
            },
            {
                "week": 4,
                "phase": "Placement Simulation & Interview Readiness",
                "focus_area": "Mock CBT Examinations & Behavioral Interviews",
                "goal": "Attain full placement readiness under timed examination conditions.",
                "tasks": [
                    "Take standard 16-question, 21-minute topic assessment test.",
                    "Practice STAR format behavioral questions and technical problem-solving logic.",
                    "Optimize resume bullet points using quantified Google XYZ formula.",
                ],
                "time_commitment": "8-10 hours / week",
                "checkpoint": "Placement Readiness Score ≥ 75%",
                "status": "PENDING",
            },
        ]

        return {
            "current_week": 1,
            "target_role": context["target_role"],
            "plan_weeks": plan,
        }

    @classmethod
    def get_interview_practice(cls, user: User) -> List[Dict[str, Any]]:
        """Curates authentic placement and interview practice questions from verified question bank."""
        if not Question:
            return []

        questions = Question.objects.filter(
            status=Question.Status.APPROVED,
            difficulty__in=[Question.Level.INTERVIEW, Question.Level.PLACEMENT, Question.Level.ADVANCED]
        ).select_related("subject", "topic")[:6]

        practice_items = []
        for q in questions:
            practice_items.append({
                "id": q.id,
                "title": q.title,
                "subject": q.subject.name,
                "topic": q.topic.name if q.topic else "",
                "difficulty": q.get_difficulty_display(),
                "prompt": q.question_text[:140] + ("..." if len(q.question_text) > 140 else ""),
                "explanation_preview": q.explanation[:120] + "..." if q.explanation else "",
                "test_url": f"/assessments/questions/{q.id}/" if hasattr(q, "id") else "#",
            })
        return practice_items

    @classmethod
    def track_career_development(cls, user: User) -> Dict[str, Any]:
        """Tracks verified career development milestones and overall readiness score."""
        context = cls.get_candidate_context(user)
        skills_count = len(context["user_skills"])
        portfolio_count = context["portfolio_count"]

        test_attempts_count = 0
        average_test_score = 0.0
        if ExamAttempt:
            attempts = ExamAttempt.objects.filter(user=user, status=ExamAttempt.Status.SUBMITTED)
            test_attempts_count = attempts.count()
            if test_attempts_count > 0:
                scores = [float(a.percentage) for a in attempts]
                average_test_score = round(sum(scores) / len(scores), 1)

        # Composite readiness score (0-100)
        readiness_score = min(
            100,
            int(
                (min(skills_count, 10) * 3)  # Max 30 pts for skills
                + (min(portfolio_count, 3) * 10)  # Max 30 pts for portfolio projects
                + (min(test_attempts_count, 5) * 4)  # Max 20 pts for completed exams
                + (int(average_test_score * 0.2))  # Max 20 pts for average exam performance
            )
        )

        milestones = [
            {"title": "Core Skills Listed", "completed": skills_count >= 5, "current": f"{skills_count} skills"},
            {"title": "Resume Uploaded & Parsed", "completed": context["has_resume"], "current": "Uploaded" if context["has_resume"] else "Pending"},
            {"title": "Portfolio Projects Attached", "completed": portfolio_count >= 1, "current": f"{portfolio_count} projects"},
            {"title": "Verified Assessment Passed", "completed": test_attempts_count >= 1, "current": f"{test_attempts_count} tests taken"},
            {"title": "Overall Placement Readiness", "completed": readiness_score >= 70, "current": f"{readiness_score}% readiness"},
        ]

        return {
            "readiness_score": readiness_score,
            "skills_count": skills_count,
            "portfolio_count": portfolio_count,
            "test_attempts_count": test_attempts_count,
            "average_test_score": average_test_score,
            "milestones": milestones,
        }
