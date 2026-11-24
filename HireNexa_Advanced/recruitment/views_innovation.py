import json
import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from accounts.models import User
from accounts.decorators import (
    candidate_required,
    recruiter_required,
    owner_required,
)
from recruitment.models import Job, Organization, Application
from recruitment.career_assistant_service import CareerAssistantService
from recruitment.market_intelligence_service import SkillMarketIntelligenceService
from recruitment.job_discovery_service import IntelligentJobDiscoveryEngine
from recruitment.company_trust_service import CompanyTrustService
from recruitment.skill_passport_service import SkillPassportService
from recruitment.recruiter_intelligence_service import RecruiterIntelligenceService
from recruitment.location_service import LocationDiscoveryService
from recruitment.notification_engine import PersonalizedNotificationEngine
from recruitment.data_intelligence_service import DataIntelligenceCenter

try:
    from assessments.exam_coach_service import ExamCoachService
    from assessments.learning_path_service import LearningPathService
except ImportError:
    ExamCoachService = None
    LearningPathService = None

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. ADVANCED AI CAREER ASSISTANT
# ==============================================================================

@login_required
def candidate_career_assistant_view(request):
    """
    Flagship context-aware AI Career Optimization (ACO) ecosystem for candidates.
    Unifies all 8 intelligence modules backed by authentic database records:
    1. Candidate Career Intelligence
    2. Skill Gap Analyzer
    3. Career Roadmap Generator
    4. Resume Optimization Intelligence
    5. Job Fit Intelligence
    6. Personalized Improvement Plan
    7. Interview Preparation Engine
    8. Career Analytics & Placement Readiness
    """
    user = request.user
    context_data = CareerAssistantService.get_candidate_context(user)
    skill_gaps = CareerAssistantService.analyze_skill_gaps(user)
    career_roadmap = CareerAssistantService.generate_career_roadmap(user)
    resume_improvements = CareerAssistantService.generate_resume_improvements(user)
    recommended_jobs = CareerAssistantService.recommend_jobs_with_reasoning(user, limit=4)
    improvement_plan = CareerAssistantService.generate_improvement_plan(user)
    interview_practice = CareerAssistantService.get_interview_practice(user)
    development_tracking = CareerAssistantService.track_career_development(user)
    learning_activities = CareerAssistantService.recommend_learning_activities(user)
    project_suggestions = CareerAssistantService.generate_project_suggestions(user)

    context = {
        "candidate": context_data,
        "skill_gaps": skill_gaps,
        "career_roadmap": career_roadmap,
        "resume_improvements": resume_improvements,
        "recommended_jobs": recommended_jobs,
        "improvement_plan": improvement_plan,
        "interview_practice": interview_practice,
        "development": development_tracking,
        "learning_activities": learning_activities,
        "project_suggestions": project_suggestions,
    }
    return render(request, "recruitment/career_assistant.html", context)


# ==============================================================================
# 2. AI SKILL MARKET INTELLIGENCE
# ==============================================================================

def market_intelligence_view(request):
    """
    Publicly accessible Skill Market Intelligence dashboard.
    Analyzes authorized platform job vacancies, skill combinations, and hiring trends.
    """
    days = int(request.GET.get("days", 90))
    intelligence_data = SkillMarketIntelligenceService.get_market_intelligence(days=days)
    return render(request, "recruitment/market_intelligence.html", {"intel": intelligence_data, "days": days})


@require_GET
def market_intelligence_api(request):
    """JSON API endpoint for market intelligence."""
    days = int(request.GET.get("days", 90))
    data = SkillMarketIntelligenceService.get_market_intelligence(days=days)
    return JsonResponse(data)


# ==============================================================================
# 3. INTELLIGENT JOB DISCOVERY
# ==============================================================================

def job_discovery_view(request):
    """
    Intelligent Job Discovery Engine with multi-factor matching and explainable reasoning.
    Allows candidates to interactively tune preferences.
    """
    user = request.user if request.user.is_authenticated else None
    
    # Extract query overrides
    overrides = {}
    work_mode = request.GET.get("work_mode")
    city = request.GET.get("city")
    target_role = request.GET.get("target_role")
    
    if work_mode:
        overrides["preferred_work_mode"] = work_mode
    if city:
        overrides["preferred_locations"] = [city]
    if target_role:
        overrides["target_role"] = target_role

    discovery_results = IntelligentJobDiscoveryEngine.discover_jobs(
        user=user, preferences_override=overrides, limit=12
    )

    context = {
        "discovery": discovery_results,
        "current_work_mode": work_mode or discovery_results["applied_preferences"].get("preferred_work_mode", "ALL"),
        "current_city": city or "",
        "current_role": target_role or discovery_results["applied_preferences"].get("target_role", ""),
    }
    return render(request, "recruitment/job_discovery.html", context)


# ==============================================================================
# 4. COMPANY TRUST AND VERIFICATION
# ==============================================================================

def company_trust_view(request, pk):
    """
    Displays verified company credentials, registration proof, address verification,
    and moderation standing.
    """
    org = get_object_or_404(Organization, pk=pk)
    trust_data = CompanyTrustService.evaluate_company_trust(org)
    return render(request, "recruitment/company_trust.html", {"trust": trust_data, "org": org})


@login_required
@require_POST
def report_suspicious_job_view(request, job_id):
    """Candidate endpoint to flag a job posting with audit trail logging."""
    reason = request.POST.get("reason", "Suspicious listing / misleading information")
    details = request.POST.get("details", "")
    
    result = CompanyTrustService.report_suspicious_job(
        reporter=request.user,
        job_id=job_id,
        reason=reason,
        details=details
    )
    if result.get("success"):
        messages.success(request, result["message"])
    else:
        messages.error(request, result.get("error", "Failed to submit report."))
    return redirect("job_detail", pk=job_id)


# ==============================================================================
# 5. AI EXAMINATION COACH
# ==============================================================================

@login_required
def exam_coach_view(request):
    """
    AI Examination Coach dashboard for weak topic detection, mistake analysis,
    and concept revision.
    """
    if not ExamCoachService:
        messages.error(request, "Examination module not installed.")
        return redirect("dashboard")

    insights = ExamCoachService.get_coach_insights(request.user)
    return render(request, "assessments/exam_coach.html", {"coach": insights})


@login_required
def exam_coach_practice_view(request):
    """
    Generates an adaptive practice session focused on candidate's detected weak topics.
    """
    if not ExamCoachService:
        return redirect("dashboard")

    topic_id = request.GET.get("topic_id")
    topic_id_int = int(topic_id) if topic_id and topic_id.isdigit() else None
    
    questions = ExamCoachService.generate_adaptive_practice_questions(
        user=request.user, topic_id=topic_id_int, num_questions=5
    )
    
    revision_notes = None
    if topic_id_int:
        revision_notes = ExamCoachService.get_concept_revision(topic_id_int)

    context = {
        "questions": questions,
        "revision_notes": revision_notes,
        "topic_id": topic_id_int,
    }
    return render(request, "assessments/coach_practice.html", context)


# ==============================================================================
# 6. SMART LEARNING PATH
# ==============================================================================

def learning_paths_view(request):
    """Curriculum catalog of smart learning paths connecting exams with career skills."""
    if not LearningPathService:
        return redirect("dashboard")

    user = request.user if request.user.is_authenticated else None
    paths = LearningPathService.list_paths(user=user)
    return render(request, "assessments/learning_paths.html", {"paths": paths})


def learning_path_detail_view(request, slug):
    """Step-by-step learning path milestone roadmap view."""
    if not LearningPathService:
        return redirect("dashboard")

    user = request.user if request.user.is_authenticated else None
    path_data = LearningPathService.get_learning_path(slug, user=user)
    if not path_data:
        messages.error(request, "Learning path not found.")
        return redirect("learning_paths")

    return render(request, "assessments/learning_path_detail.html", {"path": path_data})


# ==============================================================================
# 7. HIRENEXA PROFESSIONAL SKILL PASSPORT
# ==============================================================================

@login_required
def candidate_passport_view(request):
    """Candidate private portal view for their Professional Skill Passport."""
    passport_data = SkillPassportService.generate_passport(request.user)
    return render(request, "recruitment/skill_passport.html", {"passport": passport_data, "is_owner": True})


def public_passport_verify_view(request, passport_id):
    """
    Publicly verifiable URL for recruiters and employers to verify candidate credentials.
    Separates self-declared claims from independently verified achievements.
    """
    # Find candidate from deterministic passport hash
    # passport_id format: HNX-PASS-XXXX-XXXX-XXXX
    all_candidates = User.objects.filter(role=User.Role.CANDIDATE)
    target_candidate = None

    for cand in all_candidates:
        cand_passport = SkillPassportService.generate_passport(cand)
        if cand_passport["passport_id"] == passport_id:
            target_candidate = cand
            break

    if not target_candidate:
        return render(request, "recruitment/passport_not_found.html", {"passport_id": passport_id}, status=404)

    passport_data = SkillPassportService.generate_passport(target_candidate)
    return render(request, "recruitment/skill_passport.html", {"passport": passport_data, "is_owner": False})


# ==============================================================================
# 8. RECRUITER INTELLIGENCE DASHBOARD
# ==============================================================================

@login_required
@recruiter_required
def recruiter_intelligence_view(request):
    """
    Advanced talent acquisition analytics: applicant funnel, skill gap heatmap,
    missing job requirements, and candidate comparison matrix.
    """
    job_id = request.GET.get("job_id")
    job_id_int = int(job_id) if job_id and job_id.isdigit() else None

    pipeline_data = RecruiterIntelligenceService.get_pipeline_overview(request.user, job_id=job_id_int)
    
    comparison_data = None
    if job_id_int:
        comparison_data = RecruiterIntelligenceService.compare_candidates_for_job(job_id_int)

    context = {
        "pipeline": pipeline_data,
        "comparison": comparison_data,
        "selected_job_id": job_id_int,
    }
    return render(request, "recruitment/recruiter_intelligence.html", context)


# ==============================================================================
# 9. HIRENEXA LOCATION DISCOVERY
# ==============================================================================

def location_discovery_view(request):
    """
    Geographic nearby job discovery with distance calculation (Haversine formula),
    remote/hybrid filters, and manual or GPS coordinate lookup.
    """
    lat_str = request.GET.get("lat")
    lon_str = request.GET.get("lon")
    city = request.GET.get("city", "").strip()
    state = request.GET.get("state", "").strip()
    mode = request.GET.get("mode", "ALL")
    max_dist = float(request.GET.get("max_dist", 50.0))
    query = request.GET.get("q", "").strip()

    lat = float(lat_str) if lat_str else None
    lon = float(lon_str) if lon_str else None

    # Baseline candidate location if authenticated and no coordinates supplied
    if lat is None and not city and request.user.is_authenticated:
        profile = getattr(request.user, "candidate_profile", None)
        if profile and profile.location:
            city = profile.location

    discovery_data = LocationDiscoveryService.discover_nearby_jobs(
        candidate_lat=lat,
        candidate_lon=lon,
        city_name=city,
        state_name=state,
        workplace_mode=mode,
        max_distance_km=max_dist,
        query=query,
        limit=20,
    )

    context = {
        "location_data": discovery_data,
        "current_lat": lat,
        "current_lon": lon,
        "current_city": city,
        "current_state": state,
        "current_mode": mode,
        "current_max_dist": max_dist,
        "current_q": query,
    }
    return render(request, "recruitment/location_discovery.html", context)


# ==============================================================================
# 10. HIRENEXA PERSONALIZED NOTIFICATION ENGINE
# ==============================================================================

@login_required
def notifications_center_view(request):
    """
    Centralized notification feed respecting quiet hours and preferences.
    """
    user = request.user
    notifications_qs = user.notifications.all().order_by("-created_at")
    
    # Mark as read if POST or query param
    mark_all = request.GET.get("mark_all_read")
    if mark_all:
        notifications_qs.filter(is_read=False).update(is_read=True)
        messages.success(request, "All notifications marked as read.")
        return redirect("notifications_center")

    unread_count = notifications_qs.filter(is_read=False).count()

    context = {
        "notifications": notifications_qs[:30],
        "unread_count": unread_count,
        "preferences": user.notif_preferences,
    }
    return render(request, "recruitment/notifications_center.html", context)


# ==============================================================================
# 11. HIRENEXA DATA INTELLIGENCE CENTER
# ==============================================================================

@login_required
@owner_required
def data_intelligence_view(request):
    """
    Platform executive analytics dashboard for platform owners and administrators.
    """
    data = DataIntelligenceCenter.get_full_platform_intelligence()
    return render(request, "recruitment/data_intelligence.html", {"intel": data})
