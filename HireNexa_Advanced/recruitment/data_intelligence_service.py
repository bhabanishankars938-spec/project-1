import logging
from collections import Counter
from datetime import timedelta
from typing import Dict, Any, List
from django.utils import timezone
from django.db.models import Count, Avg, Max, Min, Q
from accounts.models import User, AuditLog
from recruitment.models import (
    Job,
    Application,
    Organization,
    Interview,
    Resume,
    ProjectPortfolio,
    City,
    State,
)

try:
    from assessments.models import (
        Question,
        Examination,
        ExamAttempt,
        ExamResponse,
        Result,
        Topic,
        Subject,
    )
except ImportError:
    Question = None
    Examination = None
    ExamAttempt = None
    ExamResponse = None
    Result = None
    Topic = None
    Subject = None

logger = logging.getLogger(__name__)


class DataIntelligenceCenter:
    """
    HireNexa Central Data Intelligence Service.
    Produces comprehensive real-time analytics across:
      1. Candidate Activity & Portfolio Velocity
      2. Job Application Pipeline Health
      3. Recruitment Stage Conversions & Time-to-Hire
      4. Examination Performance & Pass Rate Distributions
      5. Question-Bank Quality & Discrimination Diagnostics
      6. Regional Location Search Dynamics
      7. AI Recommendation Quality & Match Feedback
    All metrics are computed strictly from real database records.
    """

    @classmethod
    def get_full_platform_intelligence(cls) -> Dict[str, Any]:
        """Gathers unified multi-dimensional intelligence summary."""
        return {
            "candidate_activity": cls.get_candidate_activity_metrics(),
            "recruitment_pipeline": cls.get_recruitment_pipeline_metrics(),
            "examination_analytics": cls.get_examination_metrics(),
            "question_bank_quality": cls.get_question_bank_quality_metrics(),
            "location_dynamics": cls.get_location_search_metrics(),
            "ai_quality_metrics": cls.get_ai_recommendation_quality(),
            "generated_at": timezone.now().strftime("%B %d, %Y · %I:%M %p"),
        }

    @classmethod
    def get_candidate_activity_metrics(cls) -> Dict[str, Any]:
        """Analyzes active candidate engagement, portfolios, and resumes."""
        total_candidates = User.objects.filter(role=User.Role.CANDIDATE).count()
        candidates_with_resumes = Resume.objects.values("candidate").distinct().count()
        total_portfolios = ProjectPortfolio.objects.count()
        portfolio_authors = ProjectPortfolio.objects.values("candidate").distinct().count()

        # 30-day active candidates
        cutoff_30d = timezone.now() - timedelta(days=30)
        active_candidates_30d = User.objects.filter(
            role=User.Role.CANDIDATE, last_login__gte=cutoff_30d
        ).count()

        return {
            "total_candidates": total_candidates,
            "active_30d": active_candidates_30d,
            "active_rate_pct": round((active_candidates_30d / max(1, total_candidates)) * 100, 1),
            "candidates_with_resumes": candidates_with_resumes,
            "resume_upload_pct": round((candidates_with_resumes / max(1, total_candidates)) * 100, 1),
            "total_portfolio_projects": total_portfolios,
            "candidates_with_portfolios": portfolio_authors,
        }

    @classmethod
    def get_recruitment_pipeline_metrics(cls) -> Dict[str, Any]:
        """Analyzes active vacancies, application volume, and stage transitions."""
        total_jobs = Job.objects.count()
        active_jobs = Job.objects.filter(is_active=True, status=Job.Status.ACTIVE).count()
        total_openings = sum(Job.objects.filter(is_active=True).values_list("vacancies", flat=True) or [0])
        total_applications = Application.objects.count()

        status_counts = Counter(Application.objects.values_list("status", flat=True))

        hired_count = status_counts.get(Application.Status.HIRED, 0)
        shortlisted_count = status_counts.get(Application.Status.SHORTLISTED, 0)
        interview_count = status_counts.get(Application.Status.INTERVIEW, 0)
        rejected_count = status_counts.get(Application.Status.REJECTED, 0)

        # Average hiring funnel progression
        pipeline_conversion_pct = round((hired_count / max(1, total_applications)) * 100, 1)

        return {
            "total_jobs": total_jobs,
            "active_jobs": active_jobs,
            "total_openings_target": total_openings,
            "total_applications": total_applications,
            "hired_count": hired_count,
            "shortlisted_count": shortlisted_count,
            "interview_count": interview_count,
            "rejected_count": rejected_count,
            "conversion_rate_pct": pipeline_conversion_pct,
            "average_applicants_per_job": round(total_applications / max(1, total_jobs), 1),
        }

    @classmethod
    def get_examination_metrics(cls) -> Dict[str, Any]:
        """Evaluates exam attempts, score distributions, and pass rates."""
        if not ExamAttempt:
            return {}

        total_attempts = ExamAttempt.objects.filter(status=ExamAttempt.Status.SUBMITTED).count()
        passed_attempts = ExamAttempt.objects.filter(
            status=ExamAttempt.Status.SUBMITTED, passed=True
        ).count()

        pass_rate_pct = round((passed_attempts / max(1, total_attempts)) * 100, 1)

        # Average score and percentage
        avg_percentage = ExamAttempt.objects.filter(
            status=ExamAttempt.Status.SUBMITTED
        ).aggregate(avg=Avg("percentage"))["avg"] or 0.0

        # Subject breakdown
        subject_stats = []
        if Subject:
            for s in Subject.objects.filter(is_active=True)[:6]:
                attempts_for_subj = ExamAttempt.objects.filter(
                    examination__subject=s, status=ExamAttempt.Status.SUBMITTED
                )
                cnt = attempts_for_subj.count()
                if cnt > 0:
                    avg_p = attempts_for_subj.aggregate(avg=Avg("percentage"))["avg"] or 0.0
                    subject_stats.append({
                        "subject_name": s.name,
                        "attempts_count": cnt,
                        "average_percentage": round(avg_p, 1),
                    })

        return {
            "total_attempts": total_attempts,
            "passed_attempts": passed_attempts,
            "overall_pass_rate_pct": pass_rate_pct,
            "average_candidate_score_pct": round(float(avg_percentage), 1),
            "subject_breakdown": subject_stats,
        }

    @classmethod
    def get_question_bank_quality_metrics(cls) -> Dict[str, Any]:
        """
        Diagnoses question bank health: verified ratio, questions with highest error rates,
        and syllabus distribution.
        """
        if not Question:
            return {}

        total_questions = Question.objects.count()
        verified_questions = Question.objects.filter(is_verified=True).count()
        verified_pct = round((verified_questions / max(1, total_questions)) * 100, 1)

        # Hardest questions (highest error count)
        hardest_questions = []
        if ExamResponse:
            q_errors = (
                ExamResponse.objects.filter(is_correct=False)
                .values("question_id")
                .annotate(error_count=Count("id"))
                .order_by("-error_count")[:5]
            )
            for item in q_errors:
                q = Question.objects.filter(id=item["question_id"]).select_related("subject").first()
                if q:
                    hardest_questions.append({
                        "question_id": q.id,
                        "title": q.title,
                        "subject": q.subject.name,
                        "difficulty": q.get_difficulty_display(),
                        "error_frequency": item["error_count"],
                    })

        return {
            "total_questions": total_questions,
            "verified_questions": verified_questions,
            "verified_percentage": verified_pct,
            "hardest_diagnostic_questions": hardest_questions,
        }

    @classmethod
    def get_location_search_metrics(cls) -> Dict[str, Any]:
        """Analyzes regional job distribution and work mode preferences."""
        active_jobs = Job.objects.filter(is_active=True, status=Job.Status.ACTIVE)
        total = active_jobs.count()

        work_mode_dist = {
            "Remote": active_jobs.filter(workplace_type=Job.WorkplaceType.REMOTE).count(),
            "Hybrid": active_jobs.filter(workplace_type=Job.WorkplaceType.HYBRID).count(),
            "Onsite": active_jobs.filter(workplace_type=Job.WorkplaceType.ONSITE).count(),
        }

        # Top hiring cities
        city_counter = Counter(active_jobs.exclude(city="").values_list("city", flat=True))
        top_cities = [
            {"city": k, "job_count": v, "pct": round((v / max(1, total)) * 100, 1)}
            for k, v in city_counter.most_common(5)
        ]

        return {
            "work_mode_distribution": work_mode_dist,
            "top_hiring_cities": top_cities,
        }

    @classmethod
    def get_ai_recommendation_quality(cls) -> Dict[str, Any]:
        """Evaluates AI matching engine accuracy and score distributions."""
        scored_apps = Application.objects.filter(final_score__gt=0)
        total_scored = scored_apps.count()

        avg_score = scored_apps.aggregate(avg=Avg("final_score"))["avg"] or 0.0

        # Distribution of match scores
        high_match = scored_apps.filter(final_score__gte=75).count()
        mid_match = scored_apps.filter(final_score__gte=50, final_score__lt=75).count()
        low_match = scored_apps.filter(final_score__lt=50).count()

        return {
            "total_scored_applications": total_scored,
            "average_match_score": round(float(avg_score), 1),
            "high_match_count": high_match,
            "high_match_pct": round((high_match / max(1, total_scored)) * 100, 1),
            "mid_match_count": mid_match,
            "low_match_count": low_match,
        }
