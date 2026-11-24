import logging
from typing import Dict, Any, List, Optional
from accounts.models import User
from assessments.models import Subject, Topic, TopicProgress, ExamAttempt, CodingProblem, CodingSubmission

logger = logging.getLogger(__name__)


class LearningPathService:
    """
    Smart Learning Path Service connecting exam preparation with career industry skills.
    Maintains progressive milestone curriculums with explicit prerequisites and practical completion criteria.
    """

    # Pre-configured Industry Career Learning Paths
    CURATED_PATHS = [
        {
            "slug": "python-backend-engineer",
            "title": "Python Enterprise Backend Engineer",
            "target_role": "Backend / Python Developer",
            "estimated_weeks": 8,
            "description": "Progressive path from core programming fundamentals to production Django APIs, relational databases, and enterprise deployment.",
            "milestones": [
                {
                    "step": 1,
                    "code": "PY_FUND",
                    "title": "Python Fundamentals & Syntax",
                    "subject_keyword": "Python",
                    "prerequisites": [],
                    "theory_summary": "Variables, memory model, control flow, functions, exceptions, and data structures (lists, dicts, sets, tuples).",
                    "practical_criteria": "Score ≥ 75% on Python Fundamentals Assessment.",
                    "milestone_type": "EXAM",
                },
                {
                    "step": 2,
                    "code": "PY_OOP",
                    "title": "Object-Oriented Programming (OOP) in Python",
                    "subject_keyword": "Python",
                    "prerequisites": ["PY_FUND"],
                    "theory_summary": "Classes, inheritance, polymorphism, encapsulation, magic dunder methods, and design patterns.",
                    "practical_criteria": "Score ≥ 80% on OOP Concepts and solve 2 intermediate coding challenges.",
                    "milestone_type": "CODING",
                },
                {
                    "step": 3,
                    "code": "SQL_DB",
                    "title": "Relational Databases & SQL Mastery",
                    "subject_keyword": "SQL",
                    "prerequisites": ["PY_OOP"],
                    "theory_summary": "Schema design, ACID transactions, relational joins, indexing, query optimization, and normalization.",
                    "practical_criteria": "Pass SQL Query Assessment with ≥ 70% accuracy.",
                    "milestone_type": "EXAM",
                },
                {
                    "step": 4,
                    "code": "DJANGO_CORE",
                    "title": "Django Web Architecture & ORM",
                    "subject_keyword": "Python",
                    "prerequisites": ["SQL_DB"],
                    "theory_summary": "MVT architecture, ORM migrations, querysets, request lifecycle, authentication, middleware, and security practices.",
                    "practical_criteria": "Complete Django Web Framework Assessment and configure multi-tenant models.",
                    "milestone_type": "EXAM",
                },
                {
                    "step": 5,
                    "code": "REST_API",
                    "title": "Enterprise REST APIs & Serialization",
                    "subject_keyword": "Web",
                    "prerequisites": ["DJANGO_CORE"],
                    "theory_summary": "DRF viewsets, serializers, JWT authentication, rate limiting, and OpenAPI/Swagger documentation.",
                    "practical_criteria": "Pass DRF Assessment and build verified API endpoints.",
                    "milestone_type": "EXAM",
                },
                {
                    "step": 6,
                    "code": "GIT_DEVOPS",
                    "title": "GitHub Collaboration & CI/CD",
                    "subject_keyword": "Core",
                    "prerequisites": ["REST_API"],
                    "theory_summary": "Git branching models, pull request reviews, GitHub Actions, Docker containers, and environment secrets management.",
                    "practical_criteria": "Publish a public GitHub repository with automated test action and README.",
                    "milestone_type": "PROJECT",
                },
                {
                    "step": 7,
                    "code": "BACKEND_PROJECT",
                    "title": "Production Capstone Project",
                    "subject_keyword": "Project",
                    "prerequisites": ["GIT_DEVOPS"],
                    "theory_summary": "End-to-end full-stack web application with PostgreSQL database, auth flows, and automated test coverage.",
                    "practical_criteria": "Upload project to HireNexa Project Portfolio with live demo and source code.",
                    "milestone_type": "PORTFOLIO",
                },
                {
                    "step": 8,
                    "code": "INTERVIEW_PREP",
                    "title": "Technical Placement & Interview Prep",
                    "subject_keyword": "Interview",
                    "prerequisites": ["BACKEND_PROJECT"],
                    "theory_summary": "System design fundamentals, behavioral responses (STAR method), and data structures/algorithms mock interviews.",
                    "practical_criteria": "Score ≥ 80% on HireNexa Placement Mock Test.",
                    "milestone_type": "EXAM",
                },
            ],
        },
        {
            "slug": "mca-entrance-to-tech",
            "title": "MCA Entrance Prep & Campus Placement",
            "target_role": "MCA Candidate / Graduate Trainee",
            "estimated_weeks": 10,
            "description": "Tailored for MCA aspirants (NIMCET, OJEE, CUET-PG) integrating quantitative aptitude, logic, C/C++, DBMS, and placement coding.",
            "milestones": [
                {
                    "step": 1,
                    "code": "MATH_LOGIC",
                    "title": "Discrete Mathematics & Analytical Reasoning",
                    "subject_keyword": "Mathematics",
                    "prerequisites": [],
                    "theory_summary": "Set theory, relations, matrices, probability, permutations, and deductive reasoning.",
                    "practical_criteria": "Score ≥ 70% in MCA Entrance Math Mock Test.",
                    "milestone_type": "EXAM",
                },
                {
                    "step": 2,
                    "code": "C_DS",
                    "title": "C/C++ Programming & Data Structures",
                    "subject_keyword": "Programming",
                    "prerequisites": ["MATH_LOGIC"],
                    "theory_summary": "Pointers, dynamic memory, linked lists, stacks, queues, trees, and complexity analysis.",
                    "practical_criteria": "Solve 3 fundamental data structure coding challenges.",
                    "milestone_type": "CODING",
                },
                {
                    "step": 3,
                    "code": "CORE_CS",
                    "title": "DBMS, Operating Systems & Networking",
                    "subject_keyword": "Core",
                    "prerequisites": ["C_DS"],
                    "theory_summary": "Process management, memory paging, normalization, SQL, TCP/IP, and OSI model.",
                    "practical_criteria": "Complete Core CS Comprehensive Mock Examination.",
                    "milestone_type": "EXAM",
                },
                {
                    "step": 4,
                    "code": "CAMPUS_CODING",
                    "title": "Campus Placement Coding & Problem Solving",
                    "subject_keyword": "Interview",
                    "prerequisites": ["CORE_CS"],
                    "theory_summary": "Company hiring round aptitude, coding tests, and technical HR interview prep.",
                    "practical_criteria": "Achieve ≥ 75% on Company Placement Mock Test.",
                    "milestone_type": "EXAM",
                },
            ],
        },
    ]

    @classmethod
    def get_learning_path(cls, path_slug: str, user: Optional[User] = None) -> Optional[Dict[str, Any]]:
        """Retrieves path details and evaluates user completion status against each milestone."""
        path_def = next((p for p in cls.CURATED_PATHS if p["slug"] == path_slug), None)
        if not path_def:
            return None

        milestones_state = []
        completed_count = 0
        completed_codes = set()

        # Check user database progress
        user_topic_progress = {}
        if user and user.is_authenticated:
            for tp in TopicProgress.objects.filter(user=user):
                user_topic_progress[tp.topic.name.lower()] = tp.mastery_percentage

        for m in path_def["milestones"]:
            is_unlocked = all(p in completed_codes for p in m["prerequisites"])
            is_completed = False

            # Evaluate completion based on actual database records
            if user and user.is_authenticated and is_unlocked:
                subj = Subject.objects.filter(name__icontains=m["subject_keyword"]).first()
                if subj:
                    # Check if user has passed an exam in this subject
                    passed_exam = ExamAttempt.objects.filter(
                        user=user, examination__subject=subj, passed=True
                    ).exists()
                    if passed_exam:
                        is_completed = True
                    elif m["code"] in ["GIT_DEVOPS", "BACKEND_PROJECT"]:
                        # Check portfolio
                        has_project = user.portfolios.exists() if hasattr(user, "portfolios") else False
                        if has_project:
                            is_completed = True

            if is_completed:
                completed_count += 1
                completed_codes.add(m["code"])

            milestones_state.append({
                **m,
                "is_unlocked": is_unlocked,
                "is_completed": is_completed,
                "status": "COMPLETED" if is_completed else ("IN_PROGRESS" if is_unlocked else "LOCKED"),
            })

        total_milestones = len(path_def["milestones"])
        progress_pct = int((completed_count / max(1, total_milestones)) * 100)

        return {
            "slug": path_def["slug"],
            "title": path_def["title"],
            "target_role": path_def["target_role"],
            "description": path_def["description"],
            "estimated_weeks": path_def["estimated_weeks"],
            "total_milestones": total_milestones,
            "completed_milestones": completed_count,
            "progress_percentage": progress_pct,
            "milestones": milestones_state,
        }

    @classmethod
    def list_paths(cls, user: Optional[User] = None) -> List[Dict[str, Any]]:
        """Returns summary list of all available smart learning paths with user progress."""
        summaries = []
        for p in cls.CURATED_PATHS:
            details = cls.get_learning_path(p["slug"], user=user)
            if details:
                summaries.append({
                    "slug": details["slug"],
                    "title": details["title"],
                    "target_role": details["target_role"],
                    "description": details["description"],
                    "estimated_weeks": details["estimated_weeks"],
                    "total_milestones": details["total_milestones"],
                    "completed_milestones": details["completed_milestones"],
                    "progress_percentage": details["progress_percentage"],
                })
        return summaries
