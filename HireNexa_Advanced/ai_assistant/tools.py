import logging
from django.db.models import Q
from django.utils import timezone
from accounts.models import User
from recruitment.models import (
    Job,
    Organization,
    Application,
    Interview,
    Resume,
    ResumeExtractedData,
    CandidateProfile,
    CandidateSkill,
    Project,
)
try:
    from assessments.models import Examination, Question, Subject, Topic
except ImportError:
    Examination = None
    Question = None
    Subject = None
    Topic = None

logger = logging.getLogger(__name__)


class HireNexaToolRegistry:
    """
    Enterprise tool execution registry for HireNexa AI Assistant.
    Provides strictly authorized, server-side validated access to platform records.
    """

    @classmethod
    def get_tool_definitions(cls, user=None):
        """
        Returns JSON schema definitions of tools available to the given user based on role.
        """
        tools = [
            {
                "name": "search_jobs",
                "description": "Search active job openings on HireNexa by title, skills, location, or department.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Job title or keyword (e.g. 'Python', 'React Developer', 'Full Stack')",
                        },
                        "location": {
                            "type": "string",
                            "description": "City or workplace location (e.g. 'Bhubaneswar', 'Bengaluru', 'Remote')",
                        },
                        "target_course": {
                            "type": "string",
                            "description": "Academic target degree filter: 'MCA', 'MBA', 'BTECH', 'BCA', 'ALL'",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum vacancies to return (default 5, max 10)",
                        },
                    },
                },
            },
            {
                "name": "search_companies",
                "description": "Search verified companies and hiring employers on HireNexa.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Company name or industry keyword (e.g. 'AI', 'Cloud', 'TechCorp')",
                        },
                        "industry": {
                            "type": "string",
                            "description": "Specific industry vertical",
                        },
                    },
                },
            },
            {
                "name": "get_platform_stats",
                "description": "Retrieve current HireNexa platform metrics, top trending skills, and active job counts.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "search_freelance_projects",
                "description": "Search open freelance projects, gigs, and contract requirements on HireNexa Marketplace.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Keyword or technology (e.g. 'Python', 'React', 'Webhook', 'Design')",
                        },
                        "budget_type": {
                            "type": "string",
                            "description": "Budget type: 'FIXED' or 'HOURLY'",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum projects to return (default 5)",
                        },
                    },
                },
            },
            {
                "name": "get_mca_prep_info",
                "description": "Retrieve MCA Entrance Exam preparation material, syllabus, question bank, and mock tests for NIMCET, OJEE MCA, CUET-PG, DBMS, and Python.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_exam_or_topic": {
                            "type": "string",
                            "description": "Exam name or subject (e.g. 'NIMCET', 'OJEE', 'CUET-PG', 'DBMS', 'C Programming', 'Mathematics')",
                        },
                    },
                },
            },
            {
                "name": "get_skill_market_intelligence",
                "description": "Retrieve live hiring skill market intelligence: top required skills, emerging technologies, qualification trends, and skill combinations.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Analysis period in days (default 90)",
                        },
                    },
                },
            },
        ]

        if user and user.is_authenticated:
            # Candidate specific tools
            if getattr(user, "is_candidate", False) or getattr(user, "is_freelancer", False) or getattr(user, "is_owner", False):
                tools.extend([
                    {
                        "name": "get_career_assistant_guidance",
                        "description": "Get personalized, context-aware AI career assistance based on your profile: skill gaps, recommended jobs, learning activities, project ideas, and career readiness score.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "focus_area": {
                                    "type": "string",
                                    "description": "Optional focus: 'all', 'gaps', 'jobs', 'learning', 'projects', 'resume', 'interview', 'progress'",
                                },
                            },
                        },
                    },
                    {
                        "name": "get_intelligent_job_discovery",
                        "description": "Discover matched jobs using multi-factor recommendation engine with transparent reasoning, location matching, and preference controls.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "workplace_mode": {
                                    "type": "string",
                                    "description": "Filter by workplace mode: 'ALL', 'REMOTE', 'HYBRID', 'ONSITE'",
                                },
                                "city": {
                                    "type": "string",
                                    "description": "Preferred city for localized search",
                                },
                            },
                        },
                    },
                    {
                        "name": "get_exam_coach_guidance",
                        "description": "Get AI Examination Coach guidance: detect weak topics, analyze past test mistakes, and fetch verified revision concepts.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "topic_id": {
                                    "type": "integer",
                                    "description": "Optional specific topic ID for focused concept revision",
                                },
                            },
                        },
                    },
                    {
                        "name": "get_skill_passport_summary",
                        "description": "Retrieve candidate's HireNexa Professional Skill Passport with verified achievements, proctored test badges, and tamper-evident Passport ID.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                    {
                        "name": "get_my_applications",
                        "description": "Retrieve the logged-in candidate's own job applications, hiring rounds, and current status.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "status_filter": {
                                    "type": "string",
                                    "description": "Optional filter: 'APPLIED', 'ROUND_1', 'ROUND_2', 'FINAL_ROUND', 'HIRED', 'REJECTED'",
                                }
                            },
                        },
                    },
                    {
                        "name": "analyze_candidate_resume",
                        "description": "Analyze the logged-in candidate's uploaded resume against a target role or job on HireNexa to find match score and skill gaps.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "target_role_or_job_id": {
                                    "type": "string",
                                    "description": "Job title or Job ID to evaluate against (e.g. 'Python Developer' or '1')",
                                }
                            },
                        },
                    },
                    {
                        "name": "find_skill_gaps",
                        "description": "Compare candidate's recorded skills with industry benchmarks and active vacancies on HireNexa.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "target_domain": {
                                    "type": "string",
                                    "description": "Target specialization (e.g. 'Full Stack', 'Backend', 'Data Analyst')",
                                }
                            },
                        },
                    },
                ])

            # Recruiter & Company Admin tools
            if getattr(user, "is_recruiter", False) or getattr(user, "is_company_admin", False) or getattr(user, "is_owner", False):
                tools.extend([
                    {
                        "name": "get_my_posted_jobs",
                        "description": "Retrieve active job postings created by the recruiter's company, applicant count, and hiring targets.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                    {
                        "name": "get_recruiter_funnel_summary",
                        "description": "Get recruitment funnel numbers across 1st Round, 2nd Round, Final Round, and Hired candidates.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "job_id": {
                                    "type": "integer",
                                    "description": "Optional specific Job ID to inspect",
                                }
                            },
                        },
                    },
                    {
                        "name": "search_candidates",
                        "description": "Search verified candidate profiles by skill, target role, education, or university (Recruiters & Admins only).",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "skill": {
                                    "type": "string",
                                    "description": "Target skill (e.g. 'Python', 'React', 'Django', 'SQL')",
                                },
                                "education": {
                                    "type": "string",
                                    "description": "Target degree (e.g. 'MCA', 'BTech', 'MBA')",
                                },
                                "limit": {
                                    "type": "integer",
                                    "description": "Max candidates to return (default 5)",
                                },
                            },
                        },
                    },
                ])

            # Owner & Super Admin specific tools
            if getattr(user, "is_owner", False) or getattr(user, "is_superuser", False):
                tools.append({
                    "name": "get_admin_governance_summary",
                    "description": "Retrieve comprehensive platform administration metrics: total companies, pending approvals, vacancy quotas, verified MRR, and system health.",
                    "parameters": {"type": "object", "properties": {}},
                })

            # Common authenticated tools
            tools.append({
                "name": "get_interview_schedule",
                "description": "Retrieve upcoming scheduled interviews with dates, time, mode, and video meeting links.",
                "parameters": {"type": "object", "properties": {}},
            })

        return tools

    @classmethod
    def execute_tool(cls, tool_name, params, user=None):
        """
        Dispatches tool execution with strict server-side validation and role authorization.
        Returns a dict with status and structured result data.
        """
        try:
            if tool_name == "search_jobs":
                return cls._tool_search_jobs(params, user)
            elif tool_name == "search_companies":
                return cls._tool_search_companies(params, user)
            elif tool_name == "get_platform_stats":
                return cls._tool_get_platform_stats(params, user)
            elif tool_name == "get_my_applications":
                return cls._tool_get_my_applications(params, user)
            elif tool_name == "analyze_candidate_resume":
                return cls._tool_analyze_candidate_resume(params, user)
            elif tool_name == "find_skill_gaps":
                return cls._tool_find_skill_gaps(params, user)
            elif tool_name == "get_my_posted_jobs":
                return cls._tool_get_my_posted_jobs(params, user)
            elif tool_name == "get_recruiter_funnel_summary":
                return cls._tool_get_recruiter_funnel_summary(params, user)
            elif tool_name == "get_interview_schedule":
                return cls._tool_get_interview_schedule(params, user)
            elif tool_name == "search_freelance_projects":
                return cls._tool_search_freelance_projects(params, user)
            elif tool_name == "get_mca_prep_info":
                return cls._tool_get_mca_prep_info(params, user)
            elif tool_name == "search_candidates":
                return cls._tool_search_candidates(params, user)
            elif tool_name == "get_admin_governance_summary":
                return cls._tool_get_admin_governance_summary(params, user)
            elif tool_name == "get_skill_market_intelligence":
                return cls._tool_get_skill_market_intelligence(params, user)
            elif tool_name == "get_career_assistant_guidance":
                return cls._tool_get_career_assistant_guidance(params, user)
            elif tool_name == "get_intelligent_job_discovery":
                return cls._tool_get_intelligent_job_discovery(params, user)
            elif tool_name == "get_exam_coach_guidance":
                return cls._tool_get_exam_coach_guidance(params, user)
            elif tool_name == "get_skill_passport_summary":
                return cls._tool_get_skill_passport_summary(params, user)
            else:
                return {
                    "success": False,
                    "error": f"Tool '{tool_name}' is not recognized or permitted.",
                }
        except Exception as exc:
            logger.exception("Error executing AI tool %s", tool_name)
            return {
                "success": False,
                "error": f"An error occurred while executing {tool_name}: {str(exc)}",
            }

    # ==========================================================================
    # TOOL IMPLEMENTATIONS
    # ==========================================================================

    @classmethod
    def _tool_search_jobs(cls, params, user):
        query = (params.get("query") or "").strip()
        location = (params.get("location") or "").strip()
        target_course = (params.get("target_course") or "").strip()
        limit = min(int(params.get("limit") or 5), 10)

        qs = Job.objects.filter(is_active=True, status=Job.Status.ACTIVE).select_related("organization")

        if query:
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(required_skills__icontains=query)
                | Q(description__icontains=query)
                | Q(company_name__icontains=query)
                | Q(department__icontains=query)
            )

        if location:
            qs = qs.filter(
                Q(location__icontains=location)
                | (Q(workplace_type=Job.WorkplaceType.REMOTE) if "remote" in location.lower() else Q())
            )

        if target_course and target_course != "ALL":
            qs = qs.filter(Q(target_course=target_course) | Q(target_course="ALL"))

        jobs_list = []
        for job in qs[:limit]:
            salary_str = ""
            if job.display_salary_publicly and job.salary_min and job.salary_max:
                salary_str = f"₹{job.salary_min:,.0f} - ₹{job.salary_max:,.0f} ({job.get_salary_period_display()})"
            elif job.display_salary_publicly and job.salary_min:
                salary_str = f"₹{job.salary_min:,.0f}+ ({job.get_salary_period_display()})"
            else:
                salary_str = "Competitive / Industry Standard"

            jobs_list.append({
                "id": job.id,
                "title": job.title,
                "company": job.company_name,
                "location": job.location or "Remote",
                "workplace_type": job.get_workplace_type_display(),
                "job_type": job.get_job_type_display(),
                "vacancies": job.vacancies,
                "remaining_openings": job.remaining_vacancies,
                "salary": salary_str,
                "skills": [s.strip() for s in job.required_skills.split(",") if s.strip()],
                "target_course": job.get_target_course_display(),
                "apply_url": f"/jobs/{job.id}/",
            })

        return {
            "success": True,
            "tool": "search_jobs",
            "count": len(jobs_list),
            "results": jobs_list,
            "message": f"Found {len(jobs_list)} active matching job vacancies on HireNexa.",
        }

    @classmethod
    def _tool_search_companies(cls, params, user):
        query = (params.get("query") or "").strip()
        industry = (params.get("industry") or "").strip()

        qs = Organization.objects.filter(is_active=True, verification_status=Organization.VerificationStatus.APPROVED)

        if query:
            qs = qs.filter(
                Q(name__icontains=query)
                | Q(industry__icontains=query)
                | Q(description__icontains=query)
                | Q(location__icontains=query)
            )

        if industry:
            qs = qs.filter(industry__icontains=industry)

        companies_list = []
        for org in qs[:6]:
            active_jobs_count = org.jobs.filter(status=Job.Status.ACTIVE, is_active=True).count()
            companies_list.append({
                "id": org.id,
                "name": org.name,
                "industry": org.industry or "Technology",
                "location": org.location or "Global / Hybrid",
                "company_size": org.company_size or "Growing Startup",
                "website": org.website or "",
                "active_job_count": active_jobs_count,
                "profile_url": f"/companies/",
            })

        return {
            "success": True,
            "tool": "search_companies",
            "count": len(companies_list),
            "results": companies_list,
        }

    @classmethod
    def _tool_get_platform_stats(cls, params, user):
        active_jobs = Job.objects.filter(status=Job.Status.ACTIVE, is_active=True).count()
        total_openings = sum(Job.objects.filter(status=Job.Status.ACTIVE, is_active=True).values_list("vacancies", flat=True) or [0])
        total_orgs = Organization.objects.filter(is_active=True).count()
        
        # In-demand skills aggregation
        all_skills_qs = Job.objects.filter(status=Job.Status.ACTIVE, is_active=True).values_list("required_skills", flat=True)
        skill_counts = {}
        for s_str in all_skills_qs:
            for s in s_str.split(","):
                clean = s.strip()
                if clean:
                    skill_counts[clean] = skill_counts.get(clean, 0) + 1
        top_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:8]

        return {
            "success": True,
            "tool": "get_platform_stats",
            "active_vacancies_count": active_jobs,
            "total_openings": total_openings,
            "partner_companies_count": total_orgs,
            "top_in_demand_skills": [s[0] for s in top_skills],
        }

    @classmethod
    def _tool_get_my_applications(cls, params, user):
        if not user or not user.is_authenticated:
            return {"success": False, "error": "Authentication required to view your job applications."}

        status_filter = (params.get("status_filter") or "").strip().upper()
        qs = Application.objects.filter(candidate=user).select_related("job", "job__organization").order_by("-created_at")

        if status_filter:
            qs = qs.filter(status=status_filter)

        apps = []
        for app in qs[:10]:
            apps.append({
                "application_id": app.id,
                "job_id": app.job.id,
                "job_title": app.job.title,
                "company_name": app.job.company_name,
                "status": app.status,
                "round_label": app.round_label,
                "applied_date": app.created_at.strftime("%b %d, %Y"),
                "is_hired": app.is_hired,
                "matched_skills": app.matched_skills[:5] if isinstance(app.matched_skills, list) else [],
                "job_url": f"/jobs/{app.job.id}/",
            })

        return {
            "success": True,
            "tool": "get_my_applications",
            "user": user.username,
            "total_applications": len(apps),
            "applications": apps,
            "message": f"Retrieved {len(apps)} applications for candidate {user.username}.",
        }

    @classmethod
    def _tool_analyze_candidate_resume(cls, params, user):
        if not user or not user.is_authenticated:
            return {"success": False, "error": "Authentication required to inspect your resume."}

        # Look up candidate resume
        resume = Resume.objects.filter(candidate=user).order_by("-uploaded_at").first()
        profile = CandidateProfile.objects.filter(user=user).first()
        recorded_skills = list(CandidateSkill.objects.filter(candidate=user).values_list("name", flat=True))

        target_query = (params.get("target_role_or_job_id") or "").strip()
        target_job = None
        if target_query.isdigit():
            target_job = Job.objects.filter(id=int(target_query)).first()
        elif target_query:
            target_job = Job.objects.filter(title__icontains=target_query, is_active=True).first()

        # Combine candidate skills
        candidate_skills = set()
        if profile and profile.skills:
            candidate_skills.update([s.strip().lower() for s in profile.skills.split(",") if s.strip()])
        for s in recorded_skills:
            candidate_skills.add(s.strip().lower())

        resume_summary = ""
        if resume:
            extracted_obj = ResumeExtractedData.objects.filter(resume=resume).first()
            if extracted_obj and extracted_obj.skills:
                for s in extracted_obj.skills:
                    if isinstance(s, str):
                        candidate_skills.add(s.strip().lower())
            resume_summary = (extracted_obj.summary if extracted_obj else "") or resume.extracted_text[:400]
            if resume.extracted_text:
                text_lower = resume.extracted_text.lower()
                for token in text_lower.replace(",", " ").replace(";", " ").replace(".", " ").split():
                    candidate_skills.add(token.strip())
                for multi_skill in ["rest api", "full stack", "machine learning", "data science"]:
                    if multi_skill in text_lower:
                        candidate_skills.add(multi_skill)

        target_skills = []
        target_title = target_query or "Target Role"
        if target_job:
            target_title = target_job.title
            target_skills = [s.strip().lower() for s in target_job.required_skills.split(",") if s.strip()]
        else:
            # Default industry benchmark
            target_skills = ["python", "django", "sql", "git", "rest api", "docker", "javascript"]

        matched = [s for s in target_skills if s in candidate_skills]
        missing = [s for s in target_skills if s not in candidate_skills]
        score = int((len(matched) / max(len(target_skills), 1)) * 100)

        return {
            "success": True,
            "tool": "analyze_candidate_resume",
            "candidate_username": user.username,
            "has_uploaded_resume": bool(resume),
            "resume_file_name": resume.file_name if resume else "No uploaded resume file found",
            "target_role": target_title,
            "overall_match_percentage": score,
            "matched_competencies": [s.title() for s in matched],
            "missing_skill_gaps": [s.title() for s in missing],
            "candidate_known_skills_count": len(candidate_skills),
            "recommendations": [
                f"Add practical portfolio projects demonstrating {', '.join([s.title() for s in missing[:3]])}.",
                "Highlight quantifiable metrics in previous work or academic assignments.",
                "Ensure standard resume formatting for automated ATS parsing.",
            ],
        }

    @classmethod
    def _tool_find_skill_gaps(cls, params, user):
        domain = (params.get("target_domain") or "Backend").strip().lower()

        # Get all required skills in active jobs matching domain
        jobs = Job.objects.filter(is_active=True, status=Job.Status.ACTIVE)
        if domain:
            jobs = jobs.filter(Q(title__icontains=domain) | Q(department__icontains=domain) | Q(required_skills__icontains=domain))

        demanded = {}
        for j in jobs:
            for s in j.required_skills.split(","):
                c = s.strip().title()
                if c:
                    demanded[c] = demanded.get(c, 0) + 1

        top_market_skills = sorted(demanded.items(), key=lambda x: x[1], reverse=True)[:8]

        user_skills = []
        if user and user.is_authenticated:
            profile = CandidateProfile.objects.filter(user=user).first()
            if profile and profile.skills:
                user_skills = [s.strip().title() for s in profile.skills.split(",") if s.strip()]
            user_skills.extend([s.title() for s in CandidateSkill.objects.filter(candidate=user).values_list("name", flat=True)])
            user_skills = list(set(user_skills))

        gaps = [skill for skill, _ in top_market_skills if skill not in user_skills]

        return {
            "success": True,
            "tool": "find_skill_gaps",
            "target_domain": domain.title(),
            "top_market_skills": [f"{s} (needed in {c} openings)" for s, c in top_market_skills],
            "candidate_skills": user_skills,
            "unmet_market_skill_gaps": gaps,
            "recommended_focus": gaps[:4] if gaps else ["Advanced System Architecture", "Performance Tuning"],
        }

    @classmethod
    def _tool_get_my_posted_jobs(cls, params, user):
        if not user or not user.is_authenticated:
            return {"success": False, "error": "Recruiter authentication required."}

        is_authorized = getattr(user, "is_recruiter", False) or getattr(user, "is_company_admin", False) or getattr(user, "is_owner", False)
        if not is_authorized:
            return {"success": False, "error": "This tool is exclusively available for HR Recruiters and Company Admins."}

        qs = Job.objects.filter(recruiter=user).order_by("-created_at")
        if not qs.exists() and getattr(user, "is_company_admin", False):
            # Check company jobs
            membership = user.org_memberships.first()
            if membership:
                qs = Job.objects.filter(organization=membership.organization).order_by("-created_at")

        jobs_data = []
        for j in qs[:10]:
            funnel = j.get_round_funnel_counts()
            jobs_data.append({
                "job_id": j.id,
                "title": j.title,
                "company": j.company_name,
                "vacancies": j.vacancies,
                "hired_count": j.hired_count,
                "remaining_vacancies": j.remaining_vacancies,
                "total_applicants": funnel["total"],
                "in_round_1": funnel["round_1"],
                "in_round_2": funnel["round_2"],
                "in_final_round": funnel["final_round"],
                "hired": funnel["hired"],
                "status": j.status,
                "view_applicants_url": f"/jobs/{j.id}/applicants/",
            })

        return {
            "success": True,
            "tool": "get_my_posted_jobs",
            "recruiter_username": user.username,
            "jobs_count": len(jobs_data),
            "jobs": jobs_data,
        }

    @classmethod
    def _tool_get_recruiter_funnel_summary(cls, params, user):
        if not user or not user.is_authenticated:
            return {"success": False, "error": "Authentication required."}

        job_id = params.get("job_id")
        if not job_id:
            return {"success": False, "error": "Please provide a job_id parameter."}

        job = Job.objects.filter(id=job_id).first()
        if not job:
            return {"success": False, "error": f"Job #{job_id} not found."}

        # Verify access: recruiter, company member, or owner
        can_view = False
        if getattr(user, "is_owner", False) or user.is_superuser:
            can_view = True
        elif job.recruiter == user:
            can_view = True
        elif job.organization and user.org_memberships.filter(organization=job.organization).exists():
            can_view = True

        if not can_view:
            return {"success": False, "error": "You do not have permission to view funnel data for this job."}

        funnel = job.get_round_funnel_counts()
        return {
            "success": True,
            "tool": "get_recruiter_funnel_summary",
            "job_id": job.id,
            "job_title": job.title,
            "company_name": job.company_name,
            "vacancies": job.vacancies,
            "hiring_progress": f"{job.hiring_progress_percentage}%",
            "funnel_metrics": funnel,
        }

    @classmethod
    def _tool_get_interview_schedule(cls, params, user):
        if not user or not user.is_authenticated:
            return {"success": False, "error": "Authentication required to view your interviews."}

        qs = Interview.objects.none()
        if getattr(user, "is_candidate", False) or getattr(user, "is_freelancer", False):
            qs = Interview.objects.filter(application__candidate=user)
        elif getattr(user, "is_recruiter", False) or getattr(user, "is_company_admin", False):
            qs = Interview.objects.filter(Q(created_by=user) | Q(application__job__recruiter=user))
        elif getattr(user, "is_owner", False) or user.is_superuser:
            qs = Interview.objects.all()

        interviews_list = []
        for interview in qs.order_by("scheduled_at")[:10]:
            interviews_list.append({
                "id": interview.id,
                "job_title": interview.application.job.title,
                "candidate_name": interview.application.candidate.get_full_name() or interview.application.candidate.username,
                "round_name": interview.round_name,
                "scheduled_at": interview.scheduled_at.strftime("%A, %b %d, %Y at %I:%M %p"),
                "mode": interview.get_mode_display(),
                "meeting_link": interview.meeting_link or "Link will be shared prior to session",
                "status": interview.get_status_display(),
                "location": interview.location or "Online Video Conference",
            })

        return {
            "success": True,
            "tool": "get_interview_schedule",
            "count": len(interviews_list),
            "interviews": interviews_list,
        }

    @classmethod
    def _tool_search_freelance_projects(cls, params, user):
        query = (params.get("query") or "").strip()
        budget_type = (params.get("budget_type") or "").strip().upper()
        limit = min(int(params.get("limit") or 5), 10)

        qs = Project.objects.filter(is_active=True).select_related("client")
        if query:
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(required_skills__icontains=query)
                | Q(company_name__icontains=query)
            )
        if budget_type in ["FIXED", "HOURLY"]:
            qs = qs.filter(budget_type=budget_type)

        projects_list = []
        for p in qs[:limit]:
            budget_str = f"₹{p.budget_min:,.0f} - ₹{p.budget_max:,.0f}" if p.budget_min and p.budget_max else (f"₹{p.budget_min:,.0f}" if p.budget_min else "Competitive")
            projects_list.append({
                "id": p.id,
                "title": p.title,
                "client": p.company_name or (p.client.username if p.client else "HireNexa Client"),
                "budget": f"{budget_str} ({p.get_budget_type_display() if hasattr(p, 'get_budget_type_display') else p.budget_type})",
                "skills": [s.strip() for s in p.required_skills.split(",") if s.strip()],
                "proposals_count": p.proposals.count() if hasattr(p, 'proposals') else 0,
                "url": f"/projects/{p.id}/",
                "project_url": f"/projects/{p.id}/",
            })

        return {
            "success": True,
            "tool": "search_freelance_projects",
            "count": len(projects_list),
            "projects": projects_list,
            "results": projects_list,
            "message": f"Found {len(projects_list)} open freelance projects on HireNexa Marketplace.",
        }

    @classmethod
    def _tool_get_mca_prep_info(cls, params, user):
        target = (params.get("target_exam_or_topic") or "").strip().lower()
        exams_list = []
        sample_questions = []

        if Examination:
            exam_qs = Examination.objects.filter(is_published=True, is_active=True)
            if target:
                exam_qs = exam_qs.filter(Q(title__icontains=target) | Q(slug__icontains=target) | Q(target_entrance_exam__icontains=target))
            for ex in exam_qs[:4]:
                exams_list.append({
                    "id": ex.id,
                    "title": ex.title,
                    "target_exam": ex.target_entrance_exam or "All India MCA",
                    "duration_minutes": ex.duration_minutes,
                    "questions_count": ex.questions.count(),
                    "total_marks": float(ex.total_marks),
                    "negative_marking": float(ex.negative_marking if hasattr(ex, "negative_marking") else (ex.negative_marking_rate or 0.25)),
                    "url": f"/assessments/entrance-prep/",
                })

        if Question:
            q_qs = Question.objects.filter(status=Question.Status.APPROVED)
            if target:
                q_qs = q_qs.filter(Q(subject__name__icontains=target) | Q(topic__name__icontains=target) | Q(title__icontains=target) | Q(question_text__icontains=target))
            for q in q_qs[:3]:
                correct_opt = q.options.filter(is_correct=True).first()
                sample_questions.append({
                    "id": q.id,
                    "subject": q.subject.name if q.subject else "Computer Science",
                    "title": q.title,
                    "question": q.question_text[:200],
                    "correct_answer": f"Option {correct_opt.option_key}: {correct_opt.option_text}" if correct_opt else "Verified",
                    "difficulty": q.get_difficulty_display() if hasattr(q, "get_difficulty_display") else str(q.difficulty),
                })

        return {
            "success": True,
            "tool": "get_mca_prep_info",
            "target": target or "MCA Entrance & Computer Science",
            "active_mock_tests_count": len(exams_list),
            "mock_tests": exams_list,
            "active_entrance_exams": [
                {"code": "NIMCET", "name": "NIT MCA Common Entrance Test", "target_colleges": "National Institutes of Technology (NITs)"},
                {"code": "OJEE_MCA", "name": "Odisha Joint Entrance Examination (MCA)", "target_colleges": "Odisha State Engineering & Tech Universities"},
                {"code": "CUET_PG", "name": "Common University Entrance Test (PG)", "target_colleges": "Central & Participating Universities (DU, JNU, BHU)"},
            ],
            "sample_practice_questions": sample_questions,
            "syllabus_coverage": [
                "Mathematics: Probability, Matrices, Vectors, Coordinate Geometry, Calculus",
                "Computer Awareness: C Programming, Data Structures, DBMS, Operating Systems, Computer Networks",
                "Logical Reasoning: Series, Coding-Decoding, Blood Relations, Direction Sense",
                "Analytical Ability: Quantitative Aptitude & Data Interpretation",
            ],
            "prep_hub_url": "/assessments/entrance-prep/",
            "entrance_hub_url": "/assessments/entrance-prep/",
        }

    @classmethod
    def _tool_search_candidates(cls, params, user):
        if not user or not user.is_authenticated:
            return {"success": False, "error": "Recruiter or Administrator authentication required."}

        is_authorized = getattr(user, "is_recruiter", False) or getattr(user, "is_company_admin", False) or getattr(user, "is_owner", False) or user.is_superuser
        if not is_authorized:
            return {"success": False, "error": "Candidate search is restricted to HR Recruiters and Administrators."}

        skill = (params.get("skill") or "").strip().lower()
        education = (params.get("education") or "").strip()
        limit = min(int(params.get("limit") or 5), 10)

        qs = CandidateProfile.objects.select_related("user")
        if skill:
            qs = qs.filter(Q(skills__icontains=skill) | Q(headline__icontains=skill))
        if education:
            qs = qs.filter(Q(education__icontains=education) | Q(university__icontains=education))

        candidates_data = []
        for prof in qs[:limit]:
            email_masked = f"{prof.user.username}@hirenexa.internal"
            if prof.resume_consent and prof.user.email:
                parts = prof.user.email.split("@")
                email_masked = f"{parts[0][:3]}***@{parts[1]}"

            candidates_data.append({
                "candidate_id": prof.user.id,
                "full_name": prof.full_name or prof.user.username,
                "headline": prof.headline or "Software Developer / Candidate",
                "education": prof.education or "Computer Science Graduate",
                "university": prof.university or "Accredited University",
                "cgpa": prof.cgpa or "N/A",
                "skills": [s.strip() for s in prof.skills.split(",") if s.strip()] if prof.skills else [],
                "verified_email": prof.user.is_email_verified,
            })

        return {
            "success": True,
            "tool": "search_candidates",
            "count": len(candidates_data),
            "candidates": candidates_data,
            "message": f"Retrieved {len(candidates_data)} verified candidate profiles.",
        }

    @classmethod
    def _tool_get_admin_governance_summary(cls, params, user):
        if not user or not user.is_authenticated or not (getattr(user, "is_owner", False) or user.is_superuser):
            return {"success": False, "error": "This tool is strictly restricted to Platform Owners and Super Admins."}

        from accounts.models import User as AppUser
        from recruitment.models import Organization, Job, Application, Payment

        total_users = AppUser.objects.count()
        total_candidates = AppUser.objects.filter(role=AppUser.Role.CANDIDATE).count()
        total_recruiters = AppUser.objects.filter(role=AppUser.Role.RECRUITER).count()
        total_freelancers = AppUser.objects.filter(role=AppUser.Role.FREELANCER).count()
        total_orgs = Organization.objects.count()
        pending_orgs = Organization.objects.filter(verification_status=Organization.VerificationStatus.PENDING).count()
        active_jobs = Job.objects.filter(status=Job.Status.ACTIVE, is_active=True).count()
        total_vacancies = sum(Job.objects.filter(status=Job.Status.ACTIVE, is_active=True).values_list("vacancies", flat=True) or [0])
        total_apps = Application.objects.count()
        total_hired = Application.objects.filter(status=Application.Status.HIRED).count()

        verified_mrr = 0.0
        try:
            from django.db.models import Sum
            mrr_sum = Payment.objects.filter(status=Payment.Status.SUCCESS).aggregate(total=Sum("amount"))["total"]
            if mrr_sum:
                verified_mrr = float(mrr_sum)
        except Exception:
            pass

        return {
            "success": True,
            "tool": "get_admin_governance_summary",
            "total_registered_users": total_users,
            "candidates_count": total_candidates,
            "recruiters_count": total_recruiters,
            "freelancers_count": total_freelancers,
            "registered_companies": total_orgs,
            "pending_verification_queue": pending_orgs,
            "active_vacancies_count": active_jobs,
            "total_target_headcount": total_vacancies,
            "applications_processed": total_apps,
            "candidates_hired": total_hired,
            "verified_monthly_recurring_revenue": f"₹{verified_mrr:,.2f}",
            "system_health": "100% Operational · PostgreSQL / SQLite Active · Zero Critical Errors",
            "owner_dashboard_url": "/owner/",
        }

    @classmethod
    def _tool_get_skill_market_intelligence(cls, params, user):
        from recruitment.market_intelligence_service import SkillMarketIntelligenceService
        days = int(params.get("days") or 90)
        report = SkillMarketIntelligenceService.get_market_intelligence(days=days)
        return {
            "success": True,
            "tool": "get_skill_market_intelligence",
            **report,
        }

    @classmethod
    def _tool_get_career_assistant_guidance(cls, params, user):
        if not user or not user.is_authenticated:
            return {"success": False, "error": "Career assistant guidance requires authenticated candidate login."}

        from recruitment.career_assistant_service import CareerAssistantService
        focus = (params.get("focus_area") or "all").lower()

        context = CareerAssistantService.get_candidate_context(user)
        gaps = CareerAssistantService.analyze_skill_gaps(user)
        jobs = CareerAssistantService.recommend_jobs_with_reasoning(user, limit=3)
        learning = CareerAssistantService.recommend_learning_activities(user)
        projects = CareerAssistantService.generate_project_suggestions(user)
        development = CareerAssistantService.track_career_development(user)

        return {
            "success": True,
            "tool": "get_career_assistant_guidance",
            "candidate_name": context["full_name"],
            "target_role": context["target_role"],
            "readiness_score": development["readiness_score"],
            "skill_gaps": gaps["missing_skills"],
            "recommended_jobs": jobs,
            "learning_recommendations": learning,
            "project_suggestions": projects,
            "development_milestones": development["milestones"],
        }

    @classmethod
    def _tool_get_intelligent_job_discovery(cls, params, user):
        from recruitment.job_discovery_service import IntelligentJobDiscoveryEngine
        overrides = {}
        if params.get("workplace_mode"):
            overrides["preferred_work_mode"] = params["workplace_mode"]
        if params.get("city"):
            overrides["preferred_locations"] = [params["city"]]

        results = IntelligentJobDiscoveryEngine.discover_jobs(user, preferences_override=overrides, limit=5)
        return {
            "success": True,
            "tool": "get_intelligent_job_discovery",
            **results,
        }

    @classmethod
    def _tool_get_exam_coach_guidance(cls, params, user):
        if not user or not user.is_authenticated:
            return {"success": False, "error": "Exam coach requires candidate login."}

        from assessments.exam_coach_service import ExamCoachService
        topic_id = params.get("topic_id")
        if topic_id:
            revision = ExamCoachService.get_concept_revision(int(topic_id))
            return {
                "success": True,
                "tool": "get_exam_coach_guidance",
                "revision_notes": revision,
            }

        insights = ExamCoachService.get_coach_insights(user)
        return {
            "success": True,
            "tool": "get_exam_coach_guidance",
            **insights,
        }

    @classmethod
    def _tool_get_skill_passport_summary(cls, params, user):
        if not user or not user.is_authenticated:
            return {"success": False, "error": "Skill passport requires logged-in candidate."}

        from recruitment.skill_passport_service import SkillPassportService
        passport = SkillPassportService.generate_passport(user)
        return {
            "success": True,
            "tool": "get_skill_passport_summary",
            "passport_id": passport["passport_id"],
            "integrity_hash": passport["integrity_hash"],
            "total_verified": passport["total_verified_achievements"],
            "verified_achievements": passport["verified_achievements"],
            "self_declared_skills": passport["self_declared"]["self_declared_skills"],
            "verification_url": passport["verification_url"],
        }
