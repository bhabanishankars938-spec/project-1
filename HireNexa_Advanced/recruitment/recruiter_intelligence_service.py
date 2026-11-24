import logging
from collections import Counter
from typing import Dict, Any, List, Optional
from accounts.models import User
from recruitment.models import (
    Job,
    Application,
    Interview,
    Organization,
    OrganizationMember,
    Resume,
)

logger = logging.getLogger(__name__)


class RecruiterIntelligenceService:
    """
    Recruiter Intelligence Service for HireNexa Talent Acquisition teams.
    Provides pipeline funnel conversion, missing requirement detection,
    candidate skill comparative matrices, and automated reports.
    Governance Rule: AI assists decision-making but NEVER makes silent consequential hiring/rejection decisions.
    """

    @classmethod
    def get_pipeline_overview(cls, user: User, job_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Calculates hiring pipeline metrics across all company vacancies or for a specific job.
        """
        # Determine organization context
        org = None
        if hasattr(user, "org_memberships") and user.org_memberships.exists():
            org = user.org_memberships.first().organization
        elif hasattr(user, "recruiter_profile") and user.recruiter_profile.organization:
            org = user.recruiter_profile.organization

        jobs_qs = Job.objects.filter(is_active=True)
        if org:
            jobs_qs = jobs_qs.filter(organization=org)
        elif not (getattr(user, "is_owner", False) or user.is_superuser):
            jobs_qs = jobs_qs.filter(recruiter=user)

        if job_id:
            jobs_qs = jobs_qs.filter(id=job_id)

        apps_qs = Application.objects.filter(job__in=jobs_qs).select_related("candidate", "job", "resume")
        total_applicants = apps_qs.count()

        # Funnel stage counts
        funnel = {
            "applied": apps_qs.filter(status=Application.Status.APPLIED).count(),
            "screening": apps_qs.filter(status=Application.Status.SCREENING).count(),
            "round_1": apps_qs.filter(status=Application.Status.ROUND_1).count(),
            "round_2": apps_qs.filter(status=Application.Status.ROUND_2).count(),
            "round_3": apps_qs.filter(status=Application.Status.ROUND_3).count(),
            "final_round": apps_qs.filter(status=Application.Status.FINAL_ROUND).count(),
            "shortlisted": apps_qs.filter(status=Application.Status.SHORTLISTED).count(),
            "interview": apps_qs.filter(status=Application.Status.INTERVIEW).count(),
            "offer": apps_qs.filter(status=Application.Status.OFFER).count(),
            "hired": apps_qs.filter(status=Application.Status.HIRED).count(),
            "rejected": apps_qs.filter(status=Application.Status.REJECTED).count(),
            "withdrawn": apps_qs.filter(status=Application.Status.WITHDRAWN).count(),
        }

        # Conversion rates
        active_in_pipeline = sum([
            funnel["applied"], funnel["screening"], funnel["round_1"],
            funnel["round_2"], funnel["round_3"], funnel["final_round"],
            funnel["shortlisted"], funnel["interview"]
        ])

        hired_count = funnel["hired"]
        hire_rate = round((hired_count / max(1, total_applicants)) * 100, 1)

        # Missing Job Requirements Analysis
        # Detect skills required by the job that are missing across most applicants
        missing_skills_counter = Counter()
        matched_skills_counter = Counter()

        for app in apps_qs:
            for s in app.missing_skills:
                missing_skills_counter[s.strip().title()] += 1
            for s in app.matched_skills:
                matched_skills_counter[s.strip().title()] += 1

        missing_requirements = []
        for skill_name, missing_count in missing_skills_counter.most_common(5):
            pct_missing = round((missing_count / max(1, total_applicants)) * 100, 1)
            missing_requirements.append({
                "skill": skill_name,
                "missing_count": missing_count,
                "percentage_of_pool": pct_missing,
                "alert": f"{pct_missing}% of applicants currently lack {skill_name}.",
            })

        # Top Performing Candidates in Pipeline
        top_candidates = []
        for app in apps_qs.order_by("-final_score")[:6]:
            top_candidates.append({
                "application_id": app.id,
                "candidate_name": app.candidate.get_full_name() or app.candidate.username,
                "job_title": app.job.title,
                "status": app.get_status_display(),
                "final_score": round(app.final_score, 1),
                "skill_score": round(app.skill_score, 1),
                "matched_count": len(app.matched_skills),
                "missing_count": len(app.missing_skills),
                "recruiter_rating": app.recruiter_rating,
                "has_notes": bool(app.recruiter_notes),
            })

        return {
            "total_active_jobs": jobs_qs.filter(status=Job.Status.ACTIVE).count(),
            "total_applicants": total_applicants,
            "active_in_pipeline": active_in_pipeline,
            "hired_count": hired_count,
            "hire_rate_percentage": hire_rate,
            "funnel": funnel,
            "missing_requirements": missing_requirements,
            "top_candidates": top_candidates,
            "ai_governance_disclaimer": (
                "HireNexa AI Guard: AI matching scores and skill gap analyses serve solely as decision support. "
                "All stage advancements, shortlist inclusions, and hiring determinations require explicit recruiter action."
            ),
        }

    @classmethod
    def compare_candidates_for_job(cls, job_id: int) -> Dict[str, Any]:
        """
        Builds a side-by-side comparative matrix of applicants for a specific vacancy.
        Compares skill overlap, assessment performance, and interview status.
        """
        job = Job.objects.filter(id=job_id).first()
        if not job:
            return {"error": "Job not found"}

        required_skills = [s.strip().title() for s in job.required_skills.split(",") if s.strip()]
        apps = Application.objects.filter(job=job).select_related("candidate")[:8]

        comparison_matrix = []
        for app in apps:
            cand_skills_lower = [s.lower() for s in (app.matched_skills or [])]
            skill_matrix = {}
            for r_skill in required_skills:
                skill_matrix[r_skill] = r_skill.lower() in cand_skills_lower

            comparison_matrix.append({
                "candidate_id": app.candidate.id,
                "name": app.candidate.get_full_name() or app.candidate.username,
                "status": app.get_status_display(),
                "ai_score": round(app.final_score, 1),
                "skills_check": skill_matrix,
                "matched_count": len(app.matched_skills),
                "missing_skills": [s.title() for s in app.missing_skills],
            })

        return {
            "job_id": job.id,
            "job_title": job.title,
            "vacancies": job.vacancies,
            "required_skills": required_skills,
            "candidates": comparison_matrix,
        }
