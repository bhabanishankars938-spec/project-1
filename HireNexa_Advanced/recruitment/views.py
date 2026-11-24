import csv
import re
from datetime import datetime
from pathlib import Path
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.db.models import Count, Avg, Q, F, Sum
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User, AuditLog
from accounts.decorators import owner_required, company_admin_required, recruiter_required, candidate_required, freelancer_required
from accounts.utils import log_audit
from .forms import (
    CandidateProfileForm, CandidateEducationForm, CandidateSkillForm, CandidateProjectForm,
    ProjectPortfolioForm, RecruiterProfileForm, OrganizationForm, JobForm, ResumeUploadForm,
    InterviewForm, CreateHRForm, NewsAnnouncementForm, SubscriptionPlanForm, RejectOrgForm
)
from .models import (
    Organization, OrganizationMember, RecruiterProfile, CandidateProfile, CandidateEducation,
    CandidateSkill, CandidateProject, Job, Resume, ResumeExtractedData, Application,
    AIMatchResult, ShortlistedCandidate, Interview, Notification, Subscription, ConsentRecord,
    NewsAnnouncement, SubscriptionPlan, Payment,
    SavedJob, UserReport, CompanyVerificationDocument,
    Project, ProjectProposal, FreelancerProfile,
    Country, State, District, City, Area, PinCode,
    ProjectPortfolio, ProjectFile
)
from core.supabase_service import (
    supabase_service, CANDIDATE_PROJECTS_BUCKET, PROJECT_PREVIEWS_BUCKET,
    SupabaseService
)
from django.core.exceptions import ValidationError
from .services import (
    validate_resume_file, extract_resume_text, extract_skills, extract_education,
    extract_experience_years, calculate_match
)
from .video_interview_service import VideoInterviewService


def get_user_org(user):
    """Retrieve the primary Organization for a recruiter or company admin."""
    if not user.is_authenticated:
        return None
    # Check OrganizationMember
    membership = OrganizationMember.objects.filter(user=user, is_active=True).select_related("organization").first()
    if membership:
        return membership.organization
    # Fallback to RecruiterProfile
    if hasattr(user, "recruiter_profile") and user.recruiter_profile.organization:
        return user.recruiter_profile.organization
    return None


# ==============================================================================
# 1. PUBLIC HOME & ROUTING
# ==============================================================================

def home(request):
    jobs = Job.objects.filter(is_active=True).select_related("organization").order_by("-is_featured", "-created_at")[:6]
    total_jobs = Job.objects.filter(is_active=True).count()
    companies = Organization.objects.filter(is_active=True).annotate(
        active_jobs_count=Count("jobs", filter=Q(jobs__is_active=True))
    ).order_by("-active_jobs_count")[:6]
    companies_count = Organization.objects.filter(is_active=True).count() or Job.objects.filter(is_active=True).values("company_name").distinct().count()
    candidates_count = User.objects.filter(role=User.Role.CANDIDATE).count()
    projects = Project.objects.filter(is_active=True).order_by("-created_at")[:4]
    
    latest_news = NewsAnnouncement.objects.filter(
        is_active=True,
        target_audience__in=[NewsAnnouncement.TargetAudience.ALL, NewsAnnouncement.TargetAudience.CANDIDATES]
    ).select_related("organization").order_by("-is_pinned", "-published_at")[:6]

    popular_locations = City.objects.filter(is_metro=True).select_related("state")[:8]

    return render(request, "recruitment/home.html", {
        "jobs": jobs,
        "total_jobs": total_jobs,
        "companies": companies,
        "companies_count": companies_count,
        "candidates_count": candidates_count,
        "projects": projects,
        "latest_news": latest_news,
        "popular_locations": popular_locations,
    })


@login_required
def dashboard(request):
    """Central intelligent router sending authenticated users to their workspace."""
    if request.user.is_superuser or request.user.role == User.Role.OWNER:
        return redirect("owner_dashboard")
    elif request.user.role == User.Role.COMPANY_ADMIN:
        return redirect("company_dashboard")
    elif request.user.role == User.Role.RECRUITER:
        return redirect("hr_dashboard")
    elif request.user.role == User.Role.FREELANCER:
        return redirect("freelancer_dashboard")
    return redirect("candidate_dashboard")


# ==============================================================================
# 2. PLATFORM OWNER / SUPER ADMIN DASHBOARD
# ==============================================================================

@login_required
@owner_required
def owner_dashboard(request):
    """Platform Owner Master Dashboard with full platform administrative intelligence."""
    # 1. Core Platform KPIs (Phase 3 Strict Real Database Queries)
    total_candidates = User.objects.filter(role=User.Role.CANDIDATE).count()
    total_freelancers = User.objects.filter(role=User.Role.FREELANCER).count()
    total_companies = Organization.objects.count()
    active_companies = Organization.objects.filter(is_active=True, verification_status=Organization.VerificationStatus.APPROVED).count()
    pending_companies = Organization.objects.filter(verification_status=Organization.VerificationStatus.PENDING).count()
    suspended_companies = Organization.objects.filter(is_active=False).count()
    total_hr_users = User.objects.filter(role__in=[User.Role.RECRUITER, User.Role.COMPANY_ADMIN]).count()
    total_resumes = Resume.objects.count()
    total_jobs = Job.objects.count()
    total_active_jobs = Job.objects.filter(is_active=True).count()
    total_applications = Application.objects.count()
    total_interviews = Interview.objects.count()
    total_shortlisted = ShortlistedCandidate.objects.count()
    total_ai_processed = AIMatchResult.objects.count()
    
    # Real unique hired candidates across valid job applications
    total_hired = Application.objects.filter(status=Application.Status.HIRED).values("candidate").distinct().count()

    # Subscriptions & Verified Monthly Recurring Revenue (MRR)
    total_active_subscriptions = Subscription.objects.filter(status="ACTIVE").count()
    thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
    mrr_val = Payment.objects.filter(
        status=Payment.Status.SUCCESS,
        created_at__gte=thirty_days_ago
    ).aggregate(total=Sum("amount"))["total"] or 0.0

    # 2. Recent Entities & Approvals
    pending_orgs = Organization.objects.filter(
        verification_status=Organization.VerificationStatus.PENDING
    ).order_by("-created_at")

    recent_candidates = User.objects.filter(role=User.Role.CANDIDATE).select_related("candidate_profile").order_by("-date_joined")[:8]
    recent_hr = User.objects.filter(role__in=[User.Role.RECRUITER, User.Role.COMPANY_ADMIN]).select_related("recruiter_profile").order_by("-date_joined")[:8]
    recent_companies = Organization.objects.annotate(
        job_count=Count("jobs", distinct=True),
        member_count=Count("members", distinct=True)
    ).order_by("-created_at")[:12]
    recent_resumes = Resume.objects.select_related("candidate").order_by("-uploaded_at")[:8]
    recent_applications = Application.objects.select_related("job", "candidate", "resume").order_by("-created_at")[:10]
    recent_audit_logs = AuditLog.objects.select_related("user").order_by("-timestamp")[:12]

    # 3. Company Hiring Posts & Round Pipeline (Owner Oversight)
    company_hiring_posts = Job.objects.select_related("organization", "recruiter").prefetch_related("applications").order_by("-created_at")
    total_vacancies = sum(j.vacancies for j in company_hiring_posts)

    # 4. SaaS Subscription Plans & Recent Payments
    pricing_plans = SubscriptionPlan.objects.all().order_by("price_monthly")
    recent_payments = Payment.objects.select_related("organization").order_by("-created_at")[:8]

    # 5. System & Database Health Status
    db_engine = connection.settings_dict.get("ENGINE", "").split(".")[-1]
    is_postgres = "postgresql" in db_engine.lower()
    db_status = "Connected (Production PostgreSQL)" if is_postgres else "Connected (Development SQLite)"
    
    # 6. Announcements & News (Owner Author Broadcasts)
    announcements = NewsAnnouncement.objects.select_related("author", "organization").order_by("-created_at")[:12]
    news_form = NewsAnnouncementForm()
    all_organizations = Organization.objects.all().order_by("name")

    # 7. User Reports & Verification Documents Moderation
    pending_reports = UserReport.objects.filter(status=UserReport.Status.PENDING).select_related("reporter").order_by("-created_at")[:12]
    pending_verification_docs = CompanyVerificationDocument.objects.filter(status=CompanyVerificationDocument.Status.PENDING).select_related("organization", "submitted_by").order_by("-submitted_at")[:12]
    freelance_projects = Project.objects.select_related("client").order_by("-created_at")[:12]

    return render(request, "recruitment/owner_dashboard.html", {
        "kpis": {
            "total_candidates": total_candidates,
            "total_freelancers": total_freelancers,
            "total_companies": total_companies,
            "active_companies": active_companies,
            "pending_companies": pending_companies,
            "suspended_companies": suspended_companies,
            "total_hr_users": total_hr_users,
            "total_resumes": total_resumes,
            "total_jobs": total_jobs,
            "total_active_jobs": total_active_jobs,
            "total_applications": total_applications,
            "total_interviews": total_interviews,
            "total_shortlisted": total_shortlisted,
            "total_ai_processed": total_ai_processed,
            "total_vacancies": total_vacancies,
            "total_hired": total_hired,
            "total_active_subscriptions": total_active_subscriptions,
            "mrr": mrr_val,
        },
        "pending_orgs": pending_orgs,
        "pricing_plans": pricing_plans,
        "recent_payments": recent_payments,
        "recent_candidates": recent_candidates,
        "recent_hr": recent_hr,
        "recent_companies": recent_companies,
        "company_hiring_posts": company_hiring_posts,
        "total_vacancies": total_vacancies,
        "total_hired": total_hired,
        "recent_resumes": recent_resumes,
        "recent_applications": recent_applications,
        "recent_audit_logs": recent_audit_logs,
        "announcements": announcements,
        "news_form": news_form,
        "all_organizations": all_organizations,
        "pending_reports": pending_reports,
        "pending_verification_docs": pending_verification_docs,
        "freelance_projects": freelance_projects,
        "db_status": db_status,
        "db_engine": db_engine,
        "system_status": "Online · High Availability",
    })


@login_required
@owner_required
@require_POST
def owner_toggle_org(request, pk):
    """Platform Owner can activate, suspend, or reactivate company organizations."""
    org = get_object_or_404(Organization, pk=pk)
    org.is_active = not org.is_active
    org.save(update_fields=["is_active"])
    status_str = "Activated" if org.is_active else "Suspended"
    log_audit(request, f"ORG_{status_str.upper()}", "Organization", org.id, org.id, org.name, {"is_active": org.is_active})
    messages.success(request, f"Organization '{org.name}' has been {status_str}.")
    return redirect("owner_dashboard")


@login_required
@owner_required
@require_POST
def owner_approve_org(request, pk):
    """Platform Owner approves pending company registration."""
    org = get_object_or_404(Organization, pk=pk)
    org.verification_status = Organization.VerificationStatus.APPROVED
    org.is_active = True
    org.rejection_reason = ""
    org.save(update_fields=["verification_status", "is_active", "rejection_reason"])
    log_audit(request, "ORG_APPROVED", "Organization", org.id, org.id, org.name)
    messages.success(request, f"Organization '{org.name}' has been approved and activated.")
    return redirect("owner_dashboard")


@login_required
@owner_required
@require_POST
def owner_resolve_report(request, pk):
    """Platform Owner resolves or dismisses a moderation report."""
    report = get_object_or_404(UserReport, pk=pk)
    action = request.POST.get("action", "RESOLVE")
    notes = request.POST.get("admin_notes", "").strip()

    if action == "DISMISS":
        report.status = UserReport.Status.DISMISSED
        status_label = "Dismissed"
    else:
        report.status = UserReport.Status.RESOLVED
        status_label = "Resolved"

    report.admin_notes = notes
    report.save(update_fields=["status", "admin_notes"])
    log_audit(request, f"REPORT_{action}", "UserReport", report.id, details={"status": status_label, "notes": notes})
    messages.success(request, f"Report #{report.id} marked as {status_label}.")
    return redirect("owner_dashboard")


@login_required
@owner_required
@require_POST
def owner_review_doc(request, pk):
    """Platform Owner approves or rejects a company verification document."""
    doc = get_object_or_404(CompanyVerificationDocument, pk=pk)
    action = request.POST.get("action", "APPROVE")
    notes = request.POST.get("notes", "").strip()

    if action == "APPROVE":
        doc.status = CompanyVerificationDocument.Status.APPROVED
        status_label = "Approved"
        doc.organization.verification_status = Organization.VerificationStatus.APPROVED
        doc.organization.save(update_fields=["verification_status"])
    else:
        doc.status = CompanyVerificationDocument.Status.REJECTED
        status_label = "Rejected"

    doc.review_notes = notes
    doc.reviewed_at = timezone.now()
    doc.save(update_fields=["status", "review_notes", "reviewed_at"])
    log_audit(request, f"VERIFICATION_DOC_{action}", "CompanyVerificationDocument", doc.id, doc.organization_id, doc.organization.name, {"action": status_label})
    messages.success(request, f"Document for {doc.organization.name} marked as {status_label}.")
    return redirect("owner_dashboard")



@login_required
@owner_required
@require_POST
def owner_reject_org(request, pk):
    """Platform Owner rejects company registration with specific feedback reason."""
    org = get_object_or_404(Organization, pk=pk)
    reason = request.POST.get("rejection_reason", "").strip() or "Documentation criteria not met."
    org.verification_status = Organization.VerificationStatus.REJECTED
    org.is_active = False
    org.rejection_reason = reason
    org.save(update_fields=["verification_status", "is_active", "rejection_reason"])
    log_audit(request, "ORG_REJECTED", "Organization", org.id, org.id, org.name, {"reason": reason})
    messages.warning(request, f"Organization '{org.name}' registration was rejected.")
    return redirect("owner_dashboard")


@login_required
@owner_required
def owner_company_detail(request, pk):
    """Platform Owner deep administrative inspection of a company tenant."""
    org = get_object_or_404(Organization, pk=pk)
    members = OrganizationMember.objects.filter(organization=org).select_related("user")
    jobs = Job.objects.filter(organization=org).order_by("-created_at")
    recent_apps = Application.objects.filter(job__organization=org).select_related("job", "candidate").order_by("-created_at")[:15]
    payments = Payment.objects.filter(organization=org).order_by("-created_at")
    subscription = Subscription.objects.filter(organization=org).first()

    return render(request, "recruitment/owner_company_detail.html", {
        "org": org,
        "members": members,
        "jobs": jobs,
        "recent_apps": recent_apps,
        "payments": payments,
        "subscription": subscription,
    })


@login_required
@owner_required
def owner_plans_list(request):
    """Platform Owner manages dynamic SaaS subscription pricing plans."""
    plans = SubscriptionPlan.objects.all().order_by("price_monthly")
    return render(request, "recruitment/owner_plans.html", {"plans": plans})


@login_required
@owner_required
def owner_create_plan(request):
    """Platform Owner creates a new subscription tier."""
    form = SubscriptionPlanForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        plan = form.save()
        log_audit(request, "SUBSCRIPTION_PLAN_CREATED", "SubscriptionPlan", plan.id, details={"name": plan.name})
        messages.success(request, f"Subscription plan '{plan.name}' created.")
        return redirect("owner_dashboard")
    return render(request, "recruitment/form.html", {"form": form, "title": "Create Subscription Tier"})


@login_required
@owner_required
def owner_edit_plan(request, pk):
    """Platform Owner updates an existing subscription tier."""
    plan = get_object_or_404(SubscriptionPlan, pk=pk)
    form = SubscriptionPlanForm(request.POST or None, instance=plan)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_audit(request, "SUBSCRIPTION_PLAN_UPDATED", "SubscriptionPlan", plan.id, details={"name": plan.name})
        messages.success(request, f"Subscription plan '{plan.name}' updated.")
        return redirect("owner_dashboard")
    return render(request, "recruitment/form.html", {"form": form, "title": f"Edit Subscription Tier: {plan.name}"})


@login_required
@owner_required
@require_POST
def owner_delete_plan(request, pk):
    """Platform Owner soft-deactivates or deletes an unused plan."""
    plan = get_object_or_404(SubscriptionPlan, pk=pk)
    plan_name = plan.name
    plan.delete()
    log_audit(request, "SUBSCRIPTION_PLAN_DELETED", "SubscriptionPlan", pk, details={"name": plan_name})
    messages.success(request, f"Subscription plan '{plan_name}' deleted.")
    return redirect("owner_dashboard")


@login_required
@owner_required
def owner_export_report(request):
    """Platform Owner can export authorized recruitment platform audit reports as CSV."""
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="HireNexa_Audit_Report_{timezone.now():%Y%m%d_%H%M}.csv"'
    writer = csv.writer(response)
    writer.writerow(["Timestamp", "Actor", "Action", "Resource Type", "Resource ID", "IP Address", "Details"])
    
    logs = AuditLog.objects.select_related("user").order_by("-timestamp")[:500]
    for log in logs:
        actor_name = log.user.username if log.user else "System"
        writer.writerow([
            log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            actor_name,
            log.action,
            log.resource_type,
            log.resource_id,
            log.ip_address,
            str(log.details)
        ])
    log_audit(request, "EXPORT_AUDIT_REPORT", "AuditLog", "", details={"rows_exported": logs.count()})
    return response


# ==============================================================================
# 3. COMPANY ADMIN DASHBOARD
# ==============================================================================

@login_required
@company_admin_required
def company_dashboard(request):
    """Company Admin Workspace for organization management, HR seats, and company analytics."""
    org = get_user_org(request.user)
    if not org and (request.user.is_superuser or request.user.is_owner):
        org = Organization.objects.first()

    if not org:
        org = Organization.objects.create(
            name=f"{request.user.first_name or request.user.username}'s Company",
            is_active=True,
            verification_status=Organization.VerificationStatus.APPROVED,
        )
        OrganizationMember.objects.create(
            organization=org,
            user=request.user,
            role=OrganizationMember.MemberRole.ADMIN,
        )

    # Scoped company data
    company_jobs = Job.objects.filter(organization=org).order_by("-created_at")
    hr_members = OrganizationMember.objects.filter(organization=org).select_related("user")
    applications = Application.objects.filter(job__organization=org).select_related("job", "candidate", "resume")
    interviews = Interview.objects.filter(application__job__organization=org).select_related("application", "application__candidate")
    subscription, _ = Subscription.objects.get_or_create(organization=org)
    
    create_hr_form = CreateHRForm()

    total_vacancies = sum(j.vacancies for j in company_jobs)
    total_hired = sum(j.hired_count for j in company_jobs)

    company_news = NewsAnnouncement.objects.filter(organization=org).order_by("-created_at")[:10]
    news_form = NewsAnnouncementForm()

    return render(request, "recruitment/company_dashboard.html", {
        "org": org,
        "company_jobs": company_jobs,
        "hr_members": hr_members,
        "applications": applications,
        "interviews": interviews,
        "subscription": subscription,
        "create_hr_form": create_hr_form,
        "company_news": company_news,
        "news_form": news_form,
        "job_count": company_jobs.count(),
        "total_vacancies": total_vacancies,
        "total_hired": total_hired,
        "app_count": applications.count(),
        "shortlist_count": applications.filter(status=Application.Status.SHORTLISTED).count(),
        "interview_count": interviews.count(),
    })


@login_required
@company_admin_required
@require_POST
def company_add_hr(request):
    """Company Admin can create and provision HR recruiter accounts under their organization."""
    org = get_user_org(request.user)
    if not org:
        raise PermissionDenied("Organization not found.")

    form = CreateHRForm(request.POST)
    if form.is_valid():
        username = form.cleaned_data["username"].strip()
        email = form.cleaned_data["email"].strip().lower()
        password = form.cleaned_data["password"]
        designation = form.cleaned_data["designation"]
        department = form.cleaned_data["department"]

        if User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' is already taken.")
            return redirect("company_dashboard")
        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, f"Email '{email}' is already registered.")
            return redirect("company_dashboard")

        # Create HR user
        hr_user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            role=User.Role.RECRUITER
        )
        OrganizationMember.objects.create(
            organization=org,
            user=hr_user,
            role=OrganizationMember.MemberRole.HR,
            department=department
        )
        RecruiterProfile.objects.create(
            user=hr_user,
            organization=org,
            company_name=org.name,
            designation=designation,
            department=department
        )
        log_audit(request, "HR_ACCOUNT_CREATED", "User", hr_user.id, org.id, org.name, {"hr_username": username})
        messages.success(request, f"HR account for {username} successfully provisioned under {org.name}.")
    else:
        messages.error(request, "Invalid input. Please check the HR registration form.")
    
    return redirect("company_dashboard")


@login_required
def company_profile_edit(request):
    """Edit Organization details."""
    org = get_user_org(request.user)
    if not org:
        if request.user.role in [User.Role.COMPANY_ADMIN, User.Role.RECRUITER]:
            org = Organization.objects.create(
                name=f"{request.user.username}'s Company",
                is_active=True,
                verification_status=Organization.VerificationStatus.APPROVED,
            )
            OrganizationMember.objects.create(
                organization=org,
                user=request.user,
                role=OrganizationMember.MemberRole.ADMIN,
            )
        elif request.user.is_owner:
            org = Organization.objects.first() or Organization.objects.create(
                name="HireNexa Enterprise HQ",
                is_active=True,
                verification_status=Organization.VerificationStatus.APPROVED,
            )
        else:
            messages.warning(request, "Access restricted to Company Administrators.")
            return redirect("dashboard")

    form = OrganizationForm(request.POST or None, instance=org)
    if request.method == "POST" and form.is_valid():
        org = form.save()
        if not OrganizationMember.objects.filter(organization=org, user=request.user).exists():
            OrganizationMember.objects.create(organization=org, user=request.user, role=OrganizationMember.MemberRole.ADMIN)
        log_audit(request, "COMPANY_PROFILE_UPDATED", "Organization", org.id, org.id, org.name)
        messages.success(request, "Company profile updated.")
        return redirect("company_dashboard")

    return render(request, "recruitment/form.html", {"form": form, "title": "Edit Company Profile"})


# ==============================================================================
# 4. HR / RECRUITER DASHBOARD
# ==============================================================================

@login_required
@recruiter_required
def hr_dashboard(request):
    """
    Multi-Tenant HR Recruiter Dashboard.
    STRICT SECURITY RULE:
    HR from Company A can NEVER see Company B's jobs, applicants, or interviews.
    """
    org = get_user_org(request.user)
    
    # Query jobs strictly scoped to organization or recruiter
    if org:
        jobs = Job.objects.filter(organization=org).order_by("-created_at")
        applications = Application.objects.filter(job__organization=org).select_related("job", "candidate", "resume").order_by("-created_at")
        interviews = Interview.objects.filter(application__job__organization=org).select_related("application", "application__candidate", "application__job").order_by("scheduled_at")
    else:
        jobs = Job.objects.filter(recruiter=request.user).order_by("-created_at")
        applications = Application.objects.filter(job__recruiter=request.user).select_related("job", "candidate", "resume").order_by("-created_at")
        interviews = Interview.objects.filter(application__job__recruiter=request.user).select_related("application", "application__candidate", "application__job").order_by("scheduled_at")

    profile, _ = RecruiterProfile.objects.get_or_create(user=request.user)
    total_vacancies = sum(j.vacancies for j in jobs)
    total_hired = sum(j.hired_count for j in jobs)

    return render(request, "recruitment/recruiter_dashboard.html", {
        "org": org,
        "jobs": jobs,
        "applications": applications,
        "interviews": interviews,
        "profile": profile,
        "job_count": jobs.count(),
        "total_vacancies": total_vacancies,
        "total_hired": total_hired,
        "app_count": applications.count(),
        "shortlist_count": applications.filter(status__in=[Application.Status.SHORTLISTED, Application.Status.INTERVIEW]).count(),
    })


# ==============================================================================
# 5. CANDIDATE PORTAL & DASHBOARD
# ==============================================================================

@login_required
@candidate_required
def candidate_dashboard(request):
    """Candidate Career Portal with ATS Match Scorecards, Portfolio & Consent Management."""
    profile, _ = CandidateProfile.objects.get_or_create(user=request.user)
    applications = Application.objects.filter(candidate=request.user).select_related("job", "resume").order_by("-created_at")
    resumes = Resume.objects.filter(candidate=request.user).order_by("-uploaded_at")
    interviews = Interview.objects.filter(application__candidate=request.user).select_related("application", "application__job").order_by("scheduled_at")
    educations = CandidateEducation.objects.filter(candidate=request.user)
    skills = CandidateSkill.objects.filter(candidate=request.user)
    projects = CandidateProject.objects.filter(candidate=request.user)
    portfolios = ProjectPortfolio.objects.filter(candidate=request.user).prefetch_related("files").order_by("-created_at")
    notifications = Notification.objects.filter(recipient=request.user).order_by("-created_at")[:6]
    announcements = NewsAnnouncement.objects.filter(is_active=True).filter(
        Q(target_audience=NewsAnnouncement.TargetAudience.ALL) |
        Q(target_audience=NewsAnnouncement.TargetAudience.CANDIDATES)
    ).select_related("organization").order_by("-is_pinned", "-published_at")[:6]

    return render(request, "recruitment/candidate_dashboard.html", {
        "profile": profile,
        "applications": applications,
        "resumes": resumes,
        "interviews": interviews,
        "educations": educations,
        "skills": skills,
        "projects": projects,
        "portfolios": portfolios,
        "notifications": notifications,
        "announcements": announcements,
        "completion_rate": profile.completion_percentage(),
    })


@login_required
@candidate_required
def candidate_education_add(request):
    form = CandidateEducationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        edu = form.save(commit=False)
        edu.candidate = request.user
        edu.save()
        messages.success(request, "Education entry added to your student profile.")
        return redirect("candidate_dashboard")
    return render(request, "recruitment/form.html", {"form": form, "title": "Add Education Qualification"})


@login_required
@candidate_required
def candidate_skill_add(request):
    form = CandidateSkillForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        skill = form.save(commit=False)
        skill.candidate = request.user
        skill.save()
        messages.success(request, f"Skill '{skill.name}' added to your verified profile.")
        return redirect("candidate_dashboard")
    return render(request, "recruitment/form.html", {"form": form, "title": "Add Technical Skill"})


@login_required
@candidate_required
def candidate_project_add(request):
    form = CandidateProjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        proj = form.save(commit=False)
        proj.candidate = request.user
        proj.save()
        messages.success(request, f"Project '{proj.title}' added to your portfolio.")
        return redirect("candidate_dashboard")
    return render(request, "recruitment/form.html", {"form": form, "title": "Add Project to Portfolio"})


# ==============================================================================
# 5B. SUPABASE CANDIDATE PROJECT PORTFOLIO & HR REVIEW
# ==============================================================================

@login_required
@candidate_required
def candidate_portfolio_list(request):
    """Candidate views and manages their projects & Supabase Storage file uploads."""
    portfolios = ProjectPortfolio.objects.filter(candidate=request.user).prefetch_related("files").order_by("-created_at")
    total_files = sum(p.files.count() for p in portfolios)
    total_storage_bytes = sum(f.file_size for p in portfolios for f in p.files.all())
    
    if total_storage_bytes < 1024:
        storage_str = f"{total_storage_bytes} B"
    elif total_storage_bytes < 1024 * 1024:
        storage_str = f"{total_storage_bytes / 1024:.1f} KB"
    else:
        storage_str = f"{total_storage_bytes / (1024 * 1024):.1f} MB"

    return render(request, "recruitment/candidate_portfolio_list.html", {
        "portfolios": portfolios,
        "total_projects": portfolios.count(),
        "total_files": total_files,
        "storage_str": storage_str,
    })


@login_required
@candidate_required
def candidate_project_create(request):
    """
    Candidate creates a new project with optional multiple attachments
    stored securely in Supabase Storage bucket 'candidate-projects'.
    """
    if request.method == "POST":
        form = ProjectPortfolioForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                project = form.save(commit=False)
                project.candidate = request.user
                project.save()

                uploaded_files = request.FILES.getlist("project_files")
                saved_files_count = 0
                error_messages = []

                for f in uploaded_files:
                    try:
                        safe_name, mime_type, file_size = SupabaseService.validate_file(f)
                        storage_path = f"candidates/{request.user.id}/projects/{project.id}/{safe_name}"
                        f.seek(0)
                        file_bytes = f.read()
                        uploaded_ok = supabase_service.upload_file(
                            bucket=CANDIDATE_PROJECTS_BUCKET,
                            path=storage_path,
                            file_bytes=file_bytes,
                            content_type=mime_type,
                        )

                        if uploaded_ok:
                            ProjectFile.objects.create(
                                project=project,
                                candidate=request.user,
                                file_name=safe_name,
                                file_path=storage_path,
                                file_type=mime_type,
                                file_size=file_size,
                            )
                            saved_files_count += 1
                        else:
                            error_messages.append(f"Failed to upload '{safe_name}' to storage.")
                    except ValidationError as ve:
                        error_messages.append(f"{f.name}: {ve.message}")
                    except Exception as e:
                        error_messages.append(f"{f.name}: {str(e)}")

                log_audit(
                    request,
                    "PORTFOLIO_PROJECT_CREATED",
                    "ProjectPortfolio",
                    project.id,
                    details={"project_name": project.project_name, "files_uploaded": saved_files_count}
                )

                if error_messages:
                    for err in error_messages:
                        messages.warning(request, err)

                messages.success(
                    request,
                    f"Project '{project.project_name}' created successfully with {saved_files_count} attached file(s) in Supabase Storage."
                )
                return redirect("candidate_portfolio_list")
    else:
        form = ProjectPortfolioForm()

    return render(request, "recruitment/candidate_project_form.html", {
        "form": form,
        "title": "Add New Project to Portfolio",
        "action": "Create Project",
    })


@login_required
@candidate_required
def candidate_project_edit(request, pk):
    """Candidate edits project details and uploads additional files to Supabase Storage."""
    project = get_object_or_404(ProjectPortfolio, pk=pk, candidate=request.user)

    if request.method == "POST":
        form = ProjectPortfolioForm(request.POST, request.FILES, instance=project)
        if form.is_valid():
            with transaction.atomic():
                form.save()

                uploaded_files = request.FILES.getlist("project_files")
                saved_files_count = 0
                error_messages = []

                for f in uploaded_files:
                    try:
                        safe_name, mime_type, file_size = SupabaseService.validate_file(f)
                        storage_path = f"candidates/{request.user.id}/projects/{project.id}/{safe_name}"
                        f.seek(0)
                        file_bytes = f.read()
                        uploaded_ok = supabase_service.upload_file(
                            bucket=CANDIDATE_PROJECTS_BUCKET,
                            path=storage_path,
                            file_bytes=file_bytes,
                            content_type=mime_type,
                        )
                        if uploaded_ok:
                            ProjectFile.objects.create(
                                project=project,
                                candidate=request.user,
                                file_name=safe_name,
                                file_path=storage_path,
                                file_type=mime_type,
                                file_size=file_size,
                            )
                            saved_files_count += 1
                    except ValidationError as ve:
                        error_messages.append(f"{f.name}: {ve.message}")
                    except Exception as e:
                        error_messages.append(f"{f.name}: {str(e)}")

                if error_messages:
                    for err in error_messages:
                        messages.warning(request, err)

                log_audit(request, "PORTFOLIO_PROJECT_UPDATED", "ProjectPortfolio", project.id)
                messages.success(request, f"Project '{project.project_name}' updated successfully.")
                return redirect("candidate_portfolio_list")
    else:
        form = ProjectPortfolioForm(instance=project)

    return render(request, "recruitment/candidate_project_form.html", {
        "form": form,
        "project": project,
        "title": f"Edit Project: {project.project_name}",
        "action": "Save Changes",
    })


@login_required
@candidate_required
@require_POST
def candidate_project_delete(request, pk):
    """Candidate deletes a project and removes all its Supabase Storage files."""
    project = get_object_or_404(ProjectPortfolio, pk=pk, candidate=request.user)
    proj_name = project.project_name

    with transaction.atomic():
        for pf in project.files.all():
            supabase_service.delete_file(CANDIDATE_PROJECTS_BUCKET, pf.file_path)

        project.delete()
        log_audit(request, "PORTFOLIO_PROJECT_DELETED", "ProjectPortfolio", pk, details={"project_name": proj_name})

    messages.success(request, f"Project '{proj_name}' and all associated files deleted.")
    return redirect("candidate_portfolio_list")


@login_required
@candidate_required
@require_POST
def candidate_project_file_delete(request, pk):
    """Candidate deletes a single attached file from project and Supabase Storage."""
    file_obj = get_object_or_404(ProjectFile, pk=pk, candidate=request.user)
    proj_id = file_obj.project_id
    file_name = file_obj.file_name

    supabase_service.delete_file(CANDIDATE_PROJECTS_BUCKET, file_obj.file_path)
    file_obj.delete()
    log_audit(request, "PORTFOLIO_FILE_DELETED", "ProjectFile", pk, details={"file_name": file_name})

    messages.success(request, f"File '{file_name}' deleted.")
    return redirect("candidate_project_edit", pk=proj_id)


def _check_project_file_access(user, file_obj) -> bool:
    """
    Enforces Row Level Security (RLS) business rules for file downloads:
    1. Candidate who owns the project can access their own files.
    2. Platform Owner / Superuser has full administrative oversight.
    3. HR Recruiters and Company Admins can access files ONLY if candidate has applied
       to an active job requisition in their organization.
    """
    if not user.is_authenticated:
        return False
    if user == file_obj.candidate:
        return True
    if user.is_superuser or user.role == User.Role.OWNER:
        return True

    if user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN]:
        user_org = get_user_org(user)
        if user_org:
            has_application = Application.objects.filter(
                job__organization=user_org,
                candidate=file_obj.candidate
            ).exists()
            if has_application:
                return True

    return False


@login_required
def candidate_project_file_download(request, pk):
    """
    Generates a secure, time-limited Supabase signed URL for private file access.
    Validates ownership or hiring team authorization before granting access.
    """
    file_obj = get_object_or_404(ProjectFile, pk=pk)

    if not _check_project_file_access(request.user, file_obj):
        log_audit(request, "UNAUTHORIZED_FILE_DOWNLOAD_BLOCKED", "ProjectFile", file_obj.id)
        raise PermissionDenied("You do not have authorization to download this candidate's project file.")

    log_audit(
        request,
        "PORTFOLIO_FILE_DOWNLOADED",
        "ProjectFile",
        file_obj.id,
        details={"file_name": file_obj.file_name, "candidate_id": file_obj.candidate_id}
    )

    signed_url = file_obj.get_signed_download_url(expires_in=3600)
    if signed_url:
        return redirect(signed_url)

    raise Http404("Storage file reference could not be resolved.")


@login_required
def candidate_project_file_preview(request, pk):
    """
    Generates a secure preview for supported documents (PDF, PNG, JPG).
    """
    file_obj = get_object_or_404(ProjectFile, pk=pk)

    if not _check_project_file_access(request.user, file_obj):
        raise PermissionDenied("You do not have authorization to preview this file.")

    signed_url = file_obj.get_signed_download_url(expires_in=3600)
    if signed_url:
        return redirect(signed_url)

    raise Http404("Storage preview reference could not be resolved.")


@login_required
def hr_candidate_portfolio_view(request, candidate_id):
    """
    Dedicated view for HR Recruiters & Platform Owners to review a candidate's full
    project portfolio, technologies, screenshots, and verified files.
    """
    is_owner = request.user.is_owner or request.user.is_superuser
    is_hr = request.user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN]

    if not (is_owner or is_hr):
        raise PermissionDenied("Access restricted to authorized hiring team members.")

    candidate_user = get_object_or_404(User, pk=candidate_id, role=User.Role.CANDIDATE)
    profile = getattr(candidate_user, "candidate_profile", None)
    portfolios = ProjectPortfolio.objects.filter(candidate=candidate_user).prefetch_related("files").order_by("-created_at")

    if not is_owner:
        user_org = get_user_org(request.user)
        if not (user_org and Application.objects.filter(job__organization=user_org, candidate=candidate_user).exists()):
            raise PermissionDenied("Candidate has not applied to any position at your organization.")

    return render(request, "recruitment/hr_candidate_portfolio.html", {
        "candidate": candidate_user,
        "profile": profile,
        "portfolios": portfolios,
        "is_owner": is_owner,
    })


@login_required
@candidate_required
@require_POST
def candidate_consent_toggle(request):
    """Candidate updates their resume sharing and data processing consent."""
    profile, _ = CandidateProfile.objects.get_or_create(user=request.user)
    profile.resume_consent = not profile.resume_consent
    profile.save(update_fields=["resume_consent"])
    
    # Record consent change for audit compliance
    ConsentRecord.objects.create(
        candidate=request.user,
        consent_type="RESUME_SHARING",
        is_granted=profile.resume_consent,
        ip_address=request.META.get("REMOTE_ADDR")
    )
    status_str = "Granted" if profile.resume_consent else "Revoked"
    log_audit(request, f"CONSENT_{status_str.upper()}", "CandidateProfile", profile.id, details={"resume_consent": profile.resume_consent})
    messages.success(request, f"Resume sharing consent has been {status_str}.")
    return redirect("candidate_dashboard")


@login_required
@candidate_required
@require_POST
def candidate_delete_account(request):
    """GDPR Right-to-be-Forgotten: Candidate requests deletion of account and all personal data."""
    user = request.user
    log_audit(request, "ACCOUNT_DELETION_REQUESTED", "User", user.id, details={"username": user.username})
    with transaction.atomic():
        # Cleanly delete resumes and profile data
        for resume in user.resumes.all():
            try:
                if resume.file and Path(resume.file.path).exists():
                    Path(resume.file.path).unlink()
            except Exception:
                pass
        user.delete()
    messages.info(request, "Your account and personal data have been completely deleted from HireNexa.")
    return redirect("home")


# ==============================================================================
# 6. JOB MANAGEMENT & MULTI-COURSE DEPARTMENT TAXONOMY
# ==============================================================================

MCA_DEPARTMENT_DATA = {
    "name": "MCA (Master of Computer Applications)",
    "code": "MCA",
    "badge": "💻 MCA / IT Specialization",
    "description": "Full Stack Web Development, Software Engineering, Cloud & AI Careers",
    "roles": [
        {"title": "Full Stack Developer", "query": "full stack", "tag": "🔥 High Demand"},
        {"title": "Python & Django Developer", "query": "python", "tag": "Core Tech"},
        {"title": "Java & Spring Boot Engineer", "query": "java", "tag": "Enterprise"},
        {"title": "React & Frontend Developer", "query": "react", "tag": "UI/UX"},
        {"title": "Data Scientist & AI Specialist", "query": "machine learning", "tag": "AI/ML"},
        {"title": "Cloud & DevOps Engineer", "query": "aws", "tag": "Cloud"},
        {"title": "Mobile App Developer (Android/iOS)", "query": "mobile app", "tag": "Mobile"},
        {"title": "Database & SQL Specialist", "query": "sql", "tag": "Database"},
        {"title": "QA & Automation Tester", "query": "testing", "tag": "Testing"},
    ],
    "skills": [
        "Full Stack Development", "Python", "Django", "React", "Node.js", "Java",
        "Spring Boot", "SQL", "PostgreSQL", "MongoDB", "AWS", "Docker", "REST API", "Git"
    ]
}

MBA_DEPARTMENT_DATA = {
    "name": "MBA (Master of Business Administration)",
    "code": "MBA",
    "badge": "📊 MBA / Business Management",
    "description": "Human Resources, Digital Marketing, Financial Analysis, Business Development & Operations",
    "roles": [
        {"title": "HR Manager & Recruiter", "query": "human resources", "tag": "👥 HR & People"},
        {"title": "Talent Acquisition Specialist", "query": "talent acquisition", "tag": "Hiring"},
        {"title": "Digital Marketing Manager", "query": "digital marketing", "tag": "Marketing"},
        {"title": "Financial Analyst & Modeling", "query": "financial analysis", "tag": "Finance"},
        {"title": "Business Development (BDE/BDM)", "query": "business development", "tag": "Growth"},
        {"title": "Business & Data Analyst", "query": "business analytics", "tag": "Analytics"},
        {"title": "Product Manager", "query": "product management", "tag": "Product"},
        {"title": "Operations & Supply Chain", "query": "operations management", "tag": "Operations"},
        {"title": "Brand Strategy & Research", "query": "market research", "tag": "Strategy"},
    ],
    "skills": [
        "Human Resources", "Talent Acquisition", "Digital Marketing", "Financial Analysis",
        "Business Analytics", "Power BI", "Excel", "CRM & Salesforce", "Market Research",
        "Operations Management", "Strategic Planning", "B2B Sales"
    ]
}


def job_list(request):
    jobs = Job.objects.filter(is_active=True).select_related("organization").order_by("-created_at")
    q = request.GET.get("q", "").strip()
    skill = request.GET.get("skill", "").strip()
    location = request.GET.get("location", "").strip()
    work_mode = request.GET.get("work_mode", "").strip().upper()
    job_type = request.GET.get("type", "").strip()
    course = request.GET.get("course", "").strip().upper()
    department = request.GET.get("department", "").strip()

    all_active_jobs = jobs
    mca_count = all_active_jobs.filter(
        Q(target_course="MCA") | Q(department__icontains="mca") |
        Q(title__icontains="mca") | Q(required_skills__icontains="full stack")
    ).count()
    mba_count = all_active_jobs.filter(
        Q(target_course="MBA") | Q(department__icontains="mba") |
        Q(title__icontains="mba") | Q(required_skills__icontains="hr") |
        Q(required_skills__icontains="marketing") | Q(required_skills__icontains="finance")
    ).count()

    if course:
        if course == "MCA":
            jobs = jobs.filter(
                Q(target_course="MCA") | Q(department__icontains="mca") |
                Q(title__icontains="mca") | Q(description__icontains="mca")
            )
        elif course == "MBA":
            jobs = jobs.filter(
                Q(target_course="MBA") | Q(department__icontains="mba") |
                Q(title__icontains="mba") | Q(description__icontains="mba")
            )
        elif course in dict(Job.TargetCourse.choices):
            jobs = jobs.filter(target_course=course)

    if department:
        jobs = jobs.filter(department__icontains=department)

    if q:
        jobs = jobs.filter(
            Q(title__icontains=q) | Q(required_skills__icontains=q) |
            Q(company_name__icontains=q) | Q(description__icontains=q) |
            Q(department__icontains=q)
        )
    if skill:
        jobs = jobs.filter(
            Q(required_skills__icontains=skill) | Q(title__icontains=skill) |
            Q(description__icontains=skill)
        )

    # India Location & Workplace Mode Filtering
    req_state = request.GET.get("state", "").strip()
    req_district = request.GET.get("district", "").strip()
    req_city = request.GET.get("city", "").strip()
    req_area = request.GET.get("area", "").strip()

    if req_state and req_state.lower() not in ["all india", "india"]:
        jobs = jobs.filter(Q(state__icontains=req_state) | Q(location__icontains=req_state))
    if req_district:
        jobs = jobs.filter(Q(district__icontains=req_district) | Q(location__icontains=req_district))
    if req_city:
        jobs = jobs.filter(Q(city__icontains=req_city) | Q(location__icontains=req_city))
    if req_area:
        jobs = jobs.filter(Q(area__icontains=req_area) | Q(location__icontains=req_area))

    if location:
        loc_clean = location.strip()
        loc_lower = loc_clean.lower()
        if loc_lower in ["all india", "pan-india", "all"]:
            pass  # Matches all jobs across India
        elif loc_lower == "remote":
            jobs = jobs.filter(workplace_type=Job.WorkplaceType.REMOTE)
        elif loc_lower == "hybrid":
            jobs = jobs.filter(workplace_type=Job.WorkplaceType.HYBRID)
        elif loc_lower in ["on-site", "onsite", "office"]:
            jobs = jobs.filter(workplace_type=Job.WorkplaceType.ONSITE)
        elif ">" in loc_clean:
            # Hierarchical selection: e.g. "India > Odisha > Khordha > Bhubaneswar > Patia"
            # or "India > Odisha > Deogarh > Reamal"
            h_parts = [p.strip() for p in loc_clean.split(">") if p.strip()]
            non_india = [p for p in h_parts if p.lower() not in ["india", "all india"]]
            if non_india:
                # The deepest specified component (e.g. Patia or Bhubaneswar or Deogarh)
                deepest = non_india[-1]
                loc_q = (
                    Q(area__icontains=deepest) |
                    Q(city__icontains=deepest) |
                    Q(district__icontains=deepest) |
                    Q(state__icontains=deepest) |
                    Q(location__icontains=deepest)
                )
                # If there are broader parts (e.g. State or City), make sure it also matches
                for broader in non_india[:-1]:
                    loc_q &= (
                        Q(state__icontains=broader) |
                        Q(district__icontains=broader) |
                        Q(city__icontains=broader) |
                        Q(location__icontains=broader)
                    )
                jobs = jobs.filter(loc_q)
        elif "," in loc_clean:
            # Handle comma-separated alternative locations (e.g. 'Bengaluru, Bhubaneswar')
            # or 'City, State' pairs
            loc_parts = [p.strip() for p in loc_clean.split(",") if p.strip()]
            loc_query = Q()
            for lp in loc_parts:
                if lp.lower() == "remote":
                    loc_query |= Q(workplace_type=Job.WorkplaceType.REMOTE)
                elif lp.lower() == "hybrid":
                    loc_query |= Q(workplace_type=Job.WorkplaceType.HYBRID)
                elif lp.lower() in ["on-site", "onsite"]:
                    loc_query |= Q(workplace_type=Job.WorkplaceType.ONSITE)
                else:
                    loc_query |= (
                        Q(location__icontains=lp) |
                        Q(city__icontains=lp) |
                        Q(state__icontains=lp) |
                        Q(district__icontains=lp) |
                        Q(area__icontains=lp)
                    )
            jobs = jobs.filter(loc_query)
        else:
            # Tokenize location for multi-word or reversed-order queries (e.g. 'Odisha Deogarh', 'Deogarh Odisha')
            raw_tokens = [re.sub(r'[^a-zA-Z0-9]', '', t).strip() for t in re.split(r'[\s/\->]+', loc_clean)]
            loc_tokens = [t for t in raw_tokens if t and t.lower() not in ["india", "in", "at", "district", "dist", "state", "city"]]
            if len(loc_tokens) > 1:
                loc_multi_q = Q()
                for tok in loc_tokens:
                    loc_multi_q &= (
                        Q(location__icontains=tok) |
                        Q(city__icontains=tok) |
                        Q(state__icontains=tok) |
                        Q(district__icontains=tok) |
                        Q(area__icontains=tok)
                    )
                jobs = jobs.filter(loc_multi_q)
            elif loc_tokens:
                single_tok = loc_tokens[0]
                jobs = jobs.filter(
                    Q(location__icontains=single_tok) |
                    Q(city__icontains=single_tok) |
                    Q(state__icontains=single_tok) |
                    Q(district__icontains=single_tok) |
                    Q(area__icontains=single_tok)
                )
            else:
                jobs = jobs.filter(
                    Q(location__icontains=loc_clean) |
                    Q(city__icontains=loc_clean) |
                    Q(state__icontains=loc_clean) |
                    Q(district__icontains=loc_clean)
                )

    if work_mode:
        if work_mode == "REMOTE":
            jobs = jobs.filter(workplace_type=Job.WorkplaceType.REMOTE)
        elif work_mode == "HYBRID":
            jobs = jobs.filter(workplace_type=Job.WorkplaceType.HYBRID)
        elif work_mode in ["ON_SITE", "ONSITE"]:
            jobs = jobs.filter(workplace_type=Job.WorkplaceType.ONSITE)

    sort = request.GET.get("sort", "newest").strip().lower()
    if sort == "salary":
        jobs = jobs.order_by("-salary_max", "-created_at")
    elif sort == "vacancies":
        jobs = jobs.order_by("-vacancies", "-created_at")
    else:
        jobs = jobs.order_by("-created_at")

    if job_type:
        if job_type.lower() in ["fulltime", "full-time"]:
            jobs = jobs.filter(job_type=Job.JobType.FULL_TIME)
        elif job_type.lower() in ["freelance", "contract"]:
            jobs = jobs.filter(job_type=Job.JobType.CONTRACT)
        elif job_type.lower() == "internship":
            jobs = jobs.filter(job_type=Job.JobType.INTERNSHIP)
        elif job_type.lower() in ["parttime", "part-time"]:
            jobs = jobs.filter(job_type=Job.JobType.PART_TIME)
        else:
            jobs = jobs.filter(job_type__icontains=job_type)

    total_count = jobs.count()

    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    page_number = request.GET.get("page", 1)
    paginator = Paginator(jobs, 9)
    try:
        page_obj = paginator.get_page(page_number)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.get_page(1)

    popular_locations = City.objects.filter(is_metro=True).select_related("state")[:8]

    return render(request, "recruitment/job_list.html", {
        "jobs": page_obj,
        "page_obj": page_obj,
        "paginator": paginator,
        "sort": sort,
        "q": q,
        "skill": skill,
        "location": location,
        "state": req_state,
        "district": req_district,
        "city": req_city,
        "area": req_area,
        "work_mode": work_mode,
        "job_type": job_type,
        "course": course,
        "department": department,
        "total_count": total_count,
        "all_count": all_active_jobs.count(),
        "mca_count": mca_count,
        "mba_count": mba_count,
        "popular_locations": popular_locations,
        "mca_data": MCA_DEPARTMENT_DATA,
        "mba_data": MBA_DEPARTMENT_DATA,
    })


def job_detail(request, pk):
    job = get_object_or_404(Job, pk=pk, is_active=True)
    already_applied = False
    application = None
    if request.user.is_authenticated and request.user.role == User.Role.CANDIDATE:
        application = Application.objects.filter(job=job, candidate=request.user).first()
        already_applied = application is not None

    return render(request, "recruitment/job_detail.html", {
        "job": job,
        "already_applied": already_applied,
        "application": application,
    })


@login_required
@recruiter_required
def job_create(request):
    """Post new job opening with organization association using 6-step recruitment wizard."""
    org = get_user_org(request.user)
    form = JobForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        job = form.save(commit=False)
        job.recruiter = request.user
        job.organization = org
        job.company_name = org.name if org else (request.POST.get("company_name") or "TechCorp")
        job.save()
        log_audit(request, "JOB_CREATED", "Job", job.id, org.id if org else None, job.company_name, {"title": job.title})
        messages.success(request, f"Job '{job.title}' posted successfully.")
        return redirect("dashboard")
    return render(request, "recruitment/job_wizard.html", {"form": form, "title": "Post a New Vacancy · 6-Step Wizard", "is_edit": False})


@login_required
@recruiter_required
def job_edit(request, pk):
    """Edit existing vacancy with the 6-step recruitment wizard."""
    job = get_object_or_404(Job, pk=pk)
    org = get_user_org(request.user)
    if job.recruiter != request.user and (not org or job.organization != org) and not request.user.is_superuser and not request.user.is_owner:
        raise PermissionDenied("You do not have permission to edit this job.")

    form = JobForm(request.POST or None, instance=job)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_audit(request, "JOB_UPDATED", "Job", job.id, org.id if org else None, job.company_name)
        messages.success(request, "Job updated successfully.")
        return redirect("dashboard")
    return render(request, "recruitment/job_wizard.html", {"form": form, "job": job, "title": f"Edit Job: {job.title}", "is_edit": True})


@login_required
@recruiter_required
@require_POST
def job_duplicate(request, pk):
    """Duplicate an existing vacancy template for fast re-posting."""
    original = get_object_or_404(Job, pk=pk)
    org = get_user_org(request.user)
    if original.recruiter != request.user and (not org or original.organization != org) and not request.user.is_superuser and not request.user.is_owner:
        raise PermissionDenied("You do not have permission to duplicate this job.")

    new_job = Job.objects.create(
        recruiter=request.user,
        organization=original.organization,
        company_name=original.company_name,
        title=f"Copy of {original.title}",
        department=original.department,
        target_course=original.target_course,
        job_type=original.job_type,
        experience_level=original.experience_level,
        workplace_type=original.workplace_type,
        location=original.location,
        salary_currency=original.salary_currency,
        salary_period=original.salary_period,
        salary_min=original.salary_min,
        salary_max=original.salary_max,
        is_salary_negotiable=original.is_salary_negotiable,
        display_salary_publicly=original.display_salary_publicly,
        vacancies=original.vacancies,
        hiring_rounds=original.hiring_rounds,
        required_skills=original.required_skills,
        min_experience_years=original.min_experience_years,
        screening_questions=original.screening_questions,
        is_ai_screening_enabled=original.is_ai_screening_enabled,
        description=original.description,
        status=Job.Status.ACTIVE,
        is_active=True,
    )
    log_audit(request, "JOB_DUPLICATED", "Job", new_job.id, org.id if org else None, new_job.company_name, {"original_id": original.id})
    messages.success(request, f"Job duplicated successfully as '{new_job.title}'.")
    return redirect("job_edit", pk=new_job.pk)


@login_required
@recruiter_required
@require_POST
def job_delete(request, pk):
    """
    Safe deletion of job vacancies.
    Allows Platform Owner, Company Admin (for their org's jobs), or the posting recruiter.
    Supports action='archive' (soft delete / close) or permanent delete.
    """
    job = get_object_or_404(Job, pk=pk)
    org = get_user_org(request.user)

    can_delete = (
        request.user.is_owner or
        job.recruiter == request.user or
        (org and job.organization == org and request.user.is_company_admin)
    )
    if not can_delete:
        raise PermissionDenied("You do not have permission to delete this vacancy.")

    action = request.POST.get("action", "delete")
    job_title = job.title
    org_id = job.organization.id if job.organization else None
    org_name = job.company_name

    if action == "archive":
        job.status = Job.Status.CLOSED
        job.is_active = False
        job.save(update_fields=["status", "is_active"])
        log_audit(request, "JOB_ARCHIVED", "Job", job.id, org_id, org_name, {"title": job_title})
        messages.success(request, f"Vacancy '{job_title}' has been archived and closed to applicants.")
    else:
        app_count = job.applications.count()
        if app_count > 0 and action != "force_delete" and not request.user.is_owner:
            messages.warning(
                request,
                f"Cannot permanently delete '{job_title}' because {app_count} candidate applications are linked. Archive it or confirm force delete."
            )
            return redirect(request.META.get("HTTP_REFERER", "dashboard"))

        job.delete()
        log_audit(request, "JOB_DELETED", "Job", pk, org_id, org_name, {"title": job_title, "apps_removed": app_count})
        messages.success(request, f"Vacancy '{job_title}' was permanently deleted.")

    return redirect(request.META.get("HTTP_REFERER", "dashboard"))


@login_required
@recruiter_required
@require_POST
def job_headcount_adjust(request, pk):
    """
    In-line quick adjuster (+ / -) for vacancy headcount target.
    """
    job = get_object_or_404(Job, pk=pk)
    org = get_user_org(request.user)

    can_edit = (
        request.user.is_owner or
        job.recruiter == request.user or
        (org and job.organization == org and request.user.is_company_admin)
    )
    if not can_edit:
        raise PermissionDenied("Permission denied.")

    delta = int(request.POST.get("delta", 0))
    exact = request.POST.get("vacancies")

    if exact is not None and exact != "":
        new_vacancies = max(1, int(exact))
    else:
        new_vacancies = max(1, job.vacancies + delta)

    old_val = job.vacancies
    job.vacancies = new_vacancies

    if job.hired_count >= job.vacancies:
        job.status = Job.Status.FILLED
    elif job.status == Job.Status.FILLED:
        job.status = Job.Status.ACTIVE

    job.save(update_fields=["vacancies", "status"])
    log_audit(request, "JOB_HEADCOUNT_ADJUSTED", "Job", job.id, details={"old": old_val, "new": new_vacancies})
    messages.success(request, f"Hiring target for '{job.title}' updated to {job.vacancies} vacancies.")

    return redirect(request.META.get("HTTP_REFERER", "dashboard"))


@login_required
@recruiter_required
@require_POST
def job_toggle_status(request, pk):
    """Toggle vacancy between ACTIVE and PAUSED / CLOSED."""
    job = get_object_or_404(Job, pk=pk)
    org = get_user_org(request.user)

    can_edit = (
        request.user.is_owner or
        job.recruiter == request.user or
        (org and job.organization == org and request.user.is_company_admin)
    )
    if not can_edit:
        raise PermissionDenied("Permission denied.")

    new_status = request.POST.get("status")
    if new_status in Job.Status.values:
        job.status = new_status
        job.is_active = (new_status != Job.Status.CLOSED)
    else:
        if job.status == Job.Status.ACTIVE:
            job.status = Job.Status.PAUSED
        else:
            job.status = Job.Status.ACTIVE
            job.is_active = True

    job.save(update_fields=["status", "is_active"])
    log_audit(request, "JOB_STATUS_CHANGED", "Job", job.id, details={"status": job.status})
    messages.success(request, f"Vacancy '{job.title}' status updated to {job.get_status_display()}.")
    return redirect(request.META.get("HTTP_REFERER", "dashboard"))


@login_required
@owner_required
@require_POST
def owner_toggle_job_featured(request, pk):
    """Platform Owner can feature or unfeature vacancies on homepage."""
    job = get_object_or_404(Job, pk=pk)
    job.is_featured = not job.is_featured
    job.save(update_fields=["is_featured"])
    status_str = "Featured on Homepage" if job.is_featured else "Removed from Featured"
    log_audit(request, "JOB_FEATURE_TOGGLED", "Job", job.id, details={"is_featured": job.is_featured})
    messages.success(request, f"Vacancy '{job.title}' is now {status_str}.")
    return redirect(request.META.get("HTTP_REFERER", "owner_dashboard"))



# ==============================================================================
# 7. RESUME UPLOAD, SECURE STORAGE & AI PROCESSING
# ==============================================================================

@login_required
@candidate_required
def resume_upload(request):
    """
    Candidate uploads resume with:
    1. Validation of MIME / magic bytes and 5MB size limit.
    2. Private storage path protection.
    3. Structured text and skill extraction stored in database.
    """
    form = ResumeUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        uploaded_file = request.FILES["file"]
        is_valid, err_msg, mime_type, file_hash = validate_resume_file(uploaded_file)
        if not is_valid:
            messages.error(request, err_msg)
            return render(request, "recruitment/form.html", {"form": form, "title": "Upload Verified Resume"})

        resume = Resume(
            candidate=request.user,
            file=uploaded_file,
            file_name=uploaded_file.name,
            file_size=uploaded_file.size,
            file_hash=file_hash,
            mime_type=mime_type,
            is_verified=True,
        )
        resume.save()

        try:
            raw_text = extract_resume_text(resume.file.path)
            if not raw_text.strip():
                raise ValueError("No text could be extracted. The document may be an image-only scan.")
            
            resume.extracted_text = raw_text
            resume.save(update_fields=["extracted_text"])

            # Extract structured AI intelligence
            extracted_skills = extract_skills(raw_text)
            extracted_edu = extract_education(raw_text)
            extracted_exp = extract_experience_years(raw_text)

            ResumeExtractedData.objects.create(
                resume=resume,
                raw_text=raw_text[:20000],
                skills=extracted_skills,
                education=extracted_edu,
                experience=[{"years": extracted_exp}],
                summary=f"Extracted {len(extracted_skills)} technical competencies and {extracted_exp} years estimated experience.",
            )

            # Update candidate profile skills if currently empty
            profile = request.user.candidate_profile
            if not profile.skills and extracted_skills:
                profile.skills = ", ".join(extracted_skills[:12])
                profile.save(update_fields=["skills"])

            log_audit(request, "RESUME_UPLOADED", "Resume", resume.id, details={"file_name": uploaded_file.name, "skills_found": len(extracted_skills)})
            messages.success(request, f"Resume '{uploaded_file.name}' verified and parsed! Identified {len(extracted_skills)} technical skills.")
        except Exception as exc:
            resume.delete()
            log_audit(request, "RESUME_PROCESSING_FAILED", "Resume", "", details={"error": str(exc)})
            messages.error(request, f"Resume parsing failed: {exc}")

        return redirect("candidate_dashboard")

    return render(request, "recruitment/form.html", {"form": form, "title": "Upload Verified Resume (PDF or DOCX)"})


@login_required
def download_resume(request, pk):
    """
    Secure resume download endpoint.
    STRICT SECURITY CONTROLS:
    - Candidate can download their own resume.
    - HR can download ONLY if candidate applied to authorized company job AND consent is granted.
    - Platform Owner can download for compliance review.
    - Every download is audit-logged with downloader IP and timestamp.
    """
    resume = get_object_or_404(Resume, pk=pk)
    user = request.user
    
    is_owner = user.is_superuser or user.role == User.Role.OWNER
    is_author = resume.candidate_id == user.id
    
    # Recruiter authorization check
    is_authorized_hr = False
    if user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN]:
        org = get_user_org(user)
        if org:
            is_authorized_hr = Application.objects.filter(
                resume=resume, job__organization=org
            ).exists()
        else:
            is_authorized_hr = Application.objects.filter(
                resume=resume, job__recruiter=user
            ).exists()

    if not (is_owner or is_author or is_authorized_hr):
        log_audit(request, "UNAUTHORIZED_RESUME_DOWNLOAD_BLOCKED", "Resume", resume.id, details={"attempted_by": user.username})
        raise PermissionDenied("You do not have authorization to access this candidate's resume.")

    # Check candidate consent for external HR download
    if is_authorized_hr and not is_author and not is_owner:
        candidate_profile = getattr(resume.candidate, "candidate_profile", None)
        if candidate_profile and not candidate_profile.resume_consent:
            messages.error(request, "Candidate has withheld resume-sharing consent.")
            raise PermissionDenied("Candidate consent required.")

    # Record audit log
    log_audit(
        request, "RESUME_DOWNLOADED", "Resume", resume.id,
        details={"candidate_username": resume.candidate.username, "file_name": resume.file_name}
    )

    try:
        return FileResponse(resume.file.open("rb"), as_attachment=True, filename=resume.file_name or Path(resume.file.name).name)
    except FileNotFoundError:
        raise Http404("Resume file not found in storage.")


# ==============================================================================
# 8. APPLICATION WORKFLOW & AI SCREENING
# ==============================================================================

@login_required
@candidate_required
def apply_job(request, pk):
    """Candidate submits application with automated AI matching."""
    job = get_object_or_404(Job, pk=pk, is_active=True)
    
    if Application.objects.filter(candidate=request.user, job=job).exists():
        messages.warning(request, "You have already applied for this position.")
        return redirect("job_detail", pk=job.pk)

    resume = Resume.objects.filter(candidate=request.user, is_verified=True).order_by("-uploaded_at").first()
    if not resume or not resume.extracted_text:
        messages.error(request, "Please upload a verified resume before submitting applications.")
        return redirect("resume_upload")

    # Run AI Matching Engine
    result = calculate_match(resume.extracted_text, job.skill_list(), job.description)

    with transaction.atomic():
        app = Application.objects.create(
            candidate=request.user,
            job=job,
            resume=resume,
            status=Application.Status.APPLIED,
            matched_skills=result["matched"],
            missing_skills=result["missing"],
            skill_score=result["skill_score"],
            semantic_score=result["semantic_score"],
            final_score=result["final_score"],
            explanation=result["explanation"],
        )

        AIMatchResult.objects.create(
            application=app,
            overall_score=result["final_score"],
            skill_score=result["skill_score"],
            semantic_score=result["semantic_score"],
            matched_skills=result["matched"],
            missing_skills=result["missing"],
            explanation=result["explanation"],
            recommendation=result["recommendation"],
        )

        # Notify Recruiter
        Notification.objects.create(
            recipient=job.recruiter,
            sender=request.user,
            title=f"New Application for {job.title}",
            message=f"{request.user.username} applied for {job.title} with AI ATS match score of {result['final_score']}%.",
            notification_type=Notification.Type.APPLICATION,
            link=f"/jobs/{job.pk}/applicants/"
        )

    log_audit(request, "JOB_APPLICATION_SUBMITTED", "Application", app.id, job.organization_id, job.company_name, {"job_title": job.title, "match_score": result["final_score"]})
    messages.success(request, f"Application submitted for {job.title}! Your ATS match score is {result['final_score']}%.")
    return redirect("candidate_dashboard")


@login_required
@recruiter_required
def applicants(request, pk):
    """
    Review applicants for a job with multi-round hiring pipeline tracker.
    Access granted to: Platform Owner, Company Admin, and HR Recruiter.
    """
    job = get_object_or_404(Job, pk=pk)
    org = get_user_org(request.user)

    is_owner = request.user.is_owner or request.user.is_superuser
    is_job_recruiter = job.recruiter == request.user
    is_org_admin_or_hr = bool(org and job.organization == org)

    # Multi-tenant security check: Owner, HR, and Company Admin have access!
    if not (is_owner or is_job_recruiter or is_org_admin_or_hr):
        log_audit(request, "UNAUTHORIZED_APPLICANTS_ACCESS_BLOCKED", "Job", job.id)
        raise PermissionDenied("You do not have permission to view applicants for this job.")

    apps = job.applications.select_related(
        "candidate", "candidate__candidate_profile", "resume", "ai_result"
    ).prefetch_related(
        "candidate__portfolios", "candidate__portfolios__files"
    ).order_by("-final_score")
    
    round_filter = request.GET.get("round", "").strip()
    if round_filter:
        if round_filter == "APPLIED":
            apps = apps.filter(status__in=[Application.Status.APPLIED, Application.Status.SCREENING])
        else:
            apps = apps.filter(status=round_filter)

    funnel = job.get_round_funnel_counts()

    return render(request, "recruitment/applicants.html", {
        "job": job,
        "applications": apps,
        "status_choices": Application.Status.choices,
        "funnel": funnel,
        "round_filter": round_filter,
        "is_owner": is_owner,
        "is_company_admin": request.user.is_company_admin,
        "is_recruiter": request.user.is_recruiter,
    })


@login_required
@recruiter_required
@require_POST
def update_application_status(request, pk):
    """
    Update candidate pipeline stage / round from 1st Round to Last Round and Final Hires.
    Access granted to: Platform Owner, Company Admin, and HR Recruiter.
    """
    application = get_object_or_404(Application, pk=pk)
    org = get_user_org(request.user)

    is_owner = request.user.is_owner or request.user.is_superuser
    is_job_recruiter = application.job.recruiter == request.user
    is_org_admin_or_hr = bool(org and application.job.organization == org)

    if not (is_owner or is_job_recruiter or is_org_admin_or_hr):
        raise PermissionDenied("You do not have permission to evaluate this candidate.")

    new_status = request.POST.get("status")
    rating = request.POST.get("rating")
    notes = request.POST.get("notes")
    rejection_reason = request.POST.get("rejection_reason", "").strip()

    valid_statuses = {c[0] for c in Application.Status.choices}
    update_fields = ["updated_at"]

    if new_status and new_status in valid_statuses:
        application.status = new_status
        update_fields.append("status")
        
        # Handle Shortlisting
        if new_status == Application.Status.SHORTLISTED:
            if application.job.organization:
                ShortlistedCandidate.objects.get_or_create(
                    organization=application.job.organization,
                    job=application.job,
                    candidate=application.candidate,
                    defaults={"application": application, "shortlisted_by": request.user, "notes": notes or ""}
                )
        elif new_status == Application.Status.REJECTED:
            application.rejection_reason = rejection_reason or "Profile does not match current hiring criteria."
            update_fields.append("rejection_reason")

        # Custom notification text based on round stage
        status_label = application.get_status_display()
        if new_status == Application.Status.HIRED:
            msg = f"🎉 Congratulations! You have been selected & hired for {application.job.title} at {application.job.company_name}!"
        elif new_status in [Application.Status.ROUND_1, Application.Status.ROUND_2, Application.Status.ROUND_3, Application.Status.FINAL_ROUND]:
            msg = f"🎉 Hiring Progress: You have officially advanced to {status_label} for {application.job.title} at {application.job.company_name}."
        else:
            msg = f"Your application status for {application.job.title} at {application.job.company_name} is now: {status_label}."

        Notification.objects.create(
            recipient=application.candidate,
            sender=request.user,
            title=f"Application Update: {application.job.title} ({status_label})",
            message=msg,
            notification_type=Notification.Type.STATUS_UPDATE,
            link="/dashboard/"
        )

    if rating is not None and rating.isdigit():
        application.recruiter_rating = max(0, min(5, int(rating)))
        update_fields.append("recruiter_rating")

    if notes is not None:
        application.recruiter_notes = notes.strip()
        update_fields.append("recruiter_notes")

    application.save(update_fields=update_fields)
    log_audit(
        request, "APPLICATION_STATUS_UPDATED", "Application", application.id,
        application.job.organization_id, application.job.company_name,
        {"new_status": new_status, "candidate": application.candidate.username}
    )
    messages.success(request, f"Updated candidate {application.candidate.username} to {application.get_status_display()}.")
    return redirect("applicants", pk=application.job_id)


# ==============================================================================
# 9. INTERVIEWS & NOTIFICATIONS
# ==============================================================================

@login_required
@recruiter_required
def schedule_interview(request, pk):
    """
    Schedule candidate interview with calendar invites and audit records.
    Access granted to: Platform Owner, Company Admin, and HR Recruiter.
    """
    application = get_object_or_404(Application, pk=pk)
    org = get_user_org(request.user)

    is_owner = request.user.is_owner or request.user.is_superuser
    is_job_recruiter = application.job.recruiter == request.user
    is_org_admin_or_hr = bool(org and application.job.organization == org)

    if not (is_owner or is_job_recruiter or is_org_admin_or_hr):
        raise PermissionDenied

    form = InterviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        interview = form.save(commit=False)
        interview.application = application
        interview.created_by = request.user
        interview.save()

        # Enterprise Video Interview / Zoom provisioning
        if interview.mode == Interview.Mode.ONLINE:
            try:
                VideoInterviewService.schedule_meeting(interview, provider_type=interview.provider, host_user=request.user)
            except Exception as e:
                import logging
                logging.getLogger("hirenexa").warning(f"Video interview provisioning notice: {e}")

        application.status = Application.Status.INTERVIEW
        application.save(update_fields=["status"])

        # Notify candidate
        join_info = f" Room link: {interview.join_url}" if interview.join_url else ""
        Notification.objects.create(
            recipient=application.candidate,
            sender=request.user,
            title=f"Interview Invitation: {interview.round_name}",
            message=f"You have been invited for an interview for {application.job.title} on {interview.scheduled_at:%b %d, %Y at %I:%M %p}. Provider: {interview.get_provider_display()}.{join_info}",
            notification_type=Notification.Type.INTERVIEW,
            link=interview.join_url or "/dashboard/"
        )

        log_audit(request, "INTERVIEW_SCHEDULED", "Interview", interview.id, application.job.organization_id, application.job.company_name, {"round": interview.round_name, "candidate": application.candidate.username, "provider": interview.provider})
        messages.success(request, f"Interview scheduled for {application.candidate.username} via {interview.get_provider_display()}.")
        return redirect("applicants", pk=application.job_id)

    return render(request, "recruitment/form.html", {"form": form, "title": f"Schedule Interview: {application.candidate.username}"})


@login_required
@recruiter_required
def reschedule_interview(request, pk):
    """Recruiter reschedules an upcoming candidate interview with date/time update & notification."""
    interview = get_object_or_404(Interview, pk=pk)
    application = interview.application
    org = get_user_org(request.user)

    is_owner = request.user.is_owner or request.user.is_superuser
    is_job_recruiter = application.job.recruiter == request.user
    is_org_admin_or_hr = bool(org and application.job.organization == org)

    if not (is_owner or is_job_recruiter or is_org_admin_or_hr):
        raise PermissionDenied

    form = InterviewForm(request.POST or None, instance=interview)
    if request.method == "POST" and form.is_valid():
        interview = form.save(commit=False)
        interview.status = Interview.Status.RESCHEDULED
        interview.save()

        # Resynchronize video meeting
        if interview.mode == Interview.Mode.ONLINE:
            try:
                VideoInterviewService.schedule_meeting(interview, provider_type=interview.provider, host_user=request.user)
            except Exception as e:
                pass

        Notification.objects.create(
            recipient=application.candidate,
            sender=request.user,
            title=f"Interview Rescheduled: {interview.round_name}",
            message=f"Your interview for {application.job.title} has been rescheduled to {interview.scheduled_at:%b %d, %Y at %I:%M %p}. Mode: {interview.get_mode_display()}.",
            notification_type=Notification.Type.INTERVIEW,
            link=interview.join_url or "/dashboard/"
        )
        log_audit(request, "INTERVIEW_RESCHEDULED", "Interview", interview.id, details={"round": interview.round_name, "candidate": application.candidate.username})
        messages.success(request, f"Interview rescheduled for {application.candidate.username}.")
        return redirect("applicants", pk=application.job_id)

    return render(request, "recruitment/form.html", {"form": form, "title": f"Reschedule Interview: {application.candidate.username}"})


@login_required
@recruiter_required
@require_POST
def cancel_interview(request, pk):
    """Recruiter cancels an interview with candidate notification."""
    interview = get_object_or_404(Interview, pk=pk)
    application = interview.application
    org = get_user_org(request.user)

    is_owner = request.user.is_owner or request.user.is_superuser
    is_job_recruiter = application.job.recruiter == request.user
    is_org_admin_or_hr = bool(org and application.job.organization == org)

    if not (is_owner or is_job_recruiter or is_org_admin_or_hr):
        raise PermissionDenied

    interview.status = Interview.Status.CANCELLED
    interview.save(update_fields=["status"])

    Notification.objects.create(
        recipient=application.candidate,
        sender=request.user,
        title=f"Interview Cancelled: {interview.round_name}",
        message=f"Your interview for {application.job.title} scheduled for {interview.scheduled_at:%b %d, %Y} has been cancelled.",
        notification_type=Notification.Type.INTERVIEW,
        link="/dashboard/"
    )
    log_audit(request, "INTERVIEW_CANCELLED", "Interview", interview.id, details={"round": interview.round_name, "candidate": application.candidate.username})
    messages.success(request, f"Interview for {application.candidate.username} cancelled.")
    return redirect("applicants", pk=application.job_id)


@login_required
@login_required
def interview_lobby(request, pk):
    """
    HireNexa Pre-Join Lobby.
    Seamlessly routes candidate and interviewer directly into the Unified Connect Meeting Room.
    """
    return interview_room(request, pk)


@login_required
def interview_room(request, pk):
    """
    HireNexa Virtual Interview Gateway.
    Directs candidate and interviewer securely into the Unified HireNexa Connect Meeting Room.
    Maintains full backward compatibility for historical links, calendar invites, and bookmarks.
    """
    interview = get_object_or_404(
        Interview.objects.select_related("application", "application__candidate", "application__job", "application__job__organization"),
        pk=pk
    )
    application = interview.application
    org = get_user_org(request.user)

    is_candidate = (application.candidate == request.user)
    is_recruiter = (application.job.recruiter == request.user or bool(org and application.job.organization == org) or request.user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN])
    is_owner = bool(getattr(request.user, "is_owner", False) or request.user.is_superuser)

    if not (is_candidate or is_recruiter or is_owner):
        raise PermissionDenied("You do not have authorization to access this interview room.")

    # If external Zoom meeting with a valid direct link
    if interview.provider == Interview.Provider.ZOOM and interview.meeting_link and "zoom" in interview.meeting_link.lower():
        return redirect(interview.meeting_link)

    # Ensure synchronized HireNexa Connect Meeting
    from connect.models import Meeting, MeetingParticipant
    meeting = Meeting.objects.filter(interview=interview).first()
    if not meeting:
        host = interview.created_by or (request.user if is_recruiter else application.job.recruiter)
        meeting = Meeting.objects.create(
            title=f"Interview: {interview.round_name} - {application.job.title}",
            description=interview.notes or f"Interview for {application.job.title}",
            meeting_type=Meeting.MeetingType.ONE_TO_ONE,
            interview_round=Meeting.InterviewRound.TECHNICAL,
            status=Meeting.Status.SCHEDULED,
            host=host,
            interview=interview,
            scheduled_start=interview.scheduled_at,
            scheduled_duration_minutes=interview.duration_minutes or 45,
            waiting_room_enabled=True,
        )
        interview.meeting_id = meeting.meeting_id
        interview.meeting_link = meeting.get_absolute_url()
        interview.save(update_fields=["meeting_id", "meeting_link"])

    # Ensure both candidate and host are recorded as participants
    if application.candidate:
        MeetingParticipant.objects.get_or_create(
            meeting=meeting,
            user=application.candidate,
            defaults={"role": MeetingParticipant.Role.CANDIDATE, "status": MeetingParticipant.Status.ACCEPTED}
        )
    if meeting.host:
        MeetingParticipant.objects.get_or_create(
            meeting=meeting,
            user=meeting.host,
            defaults={"role": MeetingParticipant.Role.HOST, "status": MeetingParticipant.Status.ACCEPTED}
        )

    return redirect("connect:meeting_room", meeting_id=meeting.meeting_id)


@login_required
def profile_edit(request):
    """Edit candidate or recruiter profile + Account Trust & Verification Center."""
    if request.user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN]:
        profile, _ = RecruiterProfile.objects.get_or_create(user=request.user)
        form_class = RecruiterProfileForm
    elif request.user.role == User.Role.FREELANCER:
        profile, _ = FreelancerProfile.objects.get_or_create(user=request.user)
        form_class = CandidateProfileForm
    else:
        profile, _ = CandidateProfile.objects.get_or_create(user=request.user)
        form_class = CandidateProfileForm

    form = form_class(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        saved_profile = form.save()
        # Keep user phone number in sync if phone was entered
        new_phone = form.cleaned_data.get("phone", "").strip() if "phone" in form.cleaned_data else ""
        if new_phone and new_phone != request.user.phone_number:
            request.user.phone_number = new_phone
            request.user.save(update_fields=["phone_number"])
        messages.success(request, "Profile updated successfully.")
        return redirect("dashboard")

    return render(request, "recruitment/profile_edit.html", {
        "form": form,
        "profile": profile,
        "title": "Profile & Security Verification Center",
    })


# ==============================================================================
# 10. OWNER MANAGEMENT EXTENSIONS & FREELANCER WORKSPACE
# ==============================================================================

@login_required
@owner_required
@require_POST
def owner_toggle_user_status(request, pk):
    """Platform Owner can activate, suspend, or reactivate any user account."""
    target_user = get_object_or_404(User, pk=pk)
    if target_user == request.user:
        messages.error(request, "You cannot deactivate your own Platform Owner account.")
        return redirect("owner_dashboard")

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=["is_active"])
    status_str = "activated" if target_user.is_active else "deactivated"
    log_audit(request, f"USER_STATUS_{status_str.upper()}", "User", target_user.id, details={"target_username": target_user.username})
    messages.success(request, f"User '{target_user.username}' has been {status_str}.")
    return redirect("owner_dashboard")


@login_required
@owner_required
@require_POST
def owner_change_user_role(request, pk):
    """Platform Owner can modify user roles with full audit accountability."""
    target_user = get_object_or_404(User, pk=pk)
    new_role = request.POST.get("role")
    valid_roles = {r[0] for r in User.Role.choices}

    if new_role in valid_roles:
        old_role = target_user.role
        target_user.role = new_role
        target_user.save(update_fields=["role"])
        log_audit(request, "USER_ROLE_CHANGED", "User", target_user.id, details={"old_role": old_role, "new_role": new_role})
        messages.success(request, f"Role for '{target_user.username}' changed to {target_user.get_role_display()}.")
    else:
        messages.error(request, "Invalid role specified.")
    return redirect("owner_dashboard")


@login_required
@owner_required
@require_POST
def owner_update_setting(request):
    """Platform Owner updates platform-wide settings."""
    from accounts.models import PlatformSetting
    key = request.POST.get("key", "").strip()
    value = request.POST.get("value", "").strip()
    desc = request.POST.get("description", "").strip()

    if key:
        PlatformSetting.set_value(key, value, desc)
        log_audit(request, "SETTING_UPDATED", "PlatformSetting", key, details={"value": value})
        messages.success(request, f"Setting '{key}' updated successfully.")
    return redirect("owner_dashboard")


@login_required
@freelancer_required
def freelancer_dashboard(request):
    """Freelancer workspace for projects and proposals."""
    from recruitment.models import FreelancerProfile, ProjectProposal, Project
    profile, _ = FreelancerProfile.objects.get_or_create(user=request.user)
    proposals = ProjectProposal.objects.filter(freelancer=request.user).select_related("project").order_by("-created_at")
    available_projects = Project.objects.filter(is_active=True).order_by("-created_at")[:6]
    
    fields_to_check = [profile.hourly_rate, profile.portfolio_url, profile.github_url, profile.bio, profile.skills]
    filled = sum(1 for f in fields_to_check if f)
    completion_rate = int((filled / len(fields_to_check)) * 100) if fields_to_check else 50
    if completion_rate < 20:
        completion_rate = 20

    return render(request, "recruitment/freelancer_dashboard.html", {
        "profile": profile,
        "proposals": proposals,
        "available_projects": available_projects,
        "completion_rate": completion_rate,
    })


@login_required
@freelancer_required
def freelancer_profile_edit(request):
    from recruitment.models import FreelancerProfile
    from recruitment.forms import FreelancerProfileForm
    profile, _ = FreelancerProfile.objects.get_or_create(user=request.user)
    form = FreelancerProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Freelancer profile updated.")
        return redirect("freelancer_dashboard")
    return render(request, "recruitment/form.html", {"form": form, "title": "Edit Freelancer Profile"})


def project_list(request):
    from recruitment.models import Project
    q = request.GET.get("q", "").strip()
    skill = request.GET.get("skill", "").strip()
    projects = Project.objects.filter(is_active=True).order_by("-created_at")
    if q:
        projects = projects.filter(title__icontains=q)
    if skill:
        projects = projects.filter(required_skills__icontains=skill)
    return render(request, "recruitment/project_list.html", {
        "projects": projects,
        "total_count": projects.count(),
        "q": q,
        "skill": skill,
    })


@login_required
def project_create(request):
    from recruitment.forms import ProjectForm
    form = ProjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        proj = form.save(commit=False)
        proj.client = request.user
        proj.save()
        messages.success(request, "Project posted.")
        return redirect("dashboard")
    return render(request, "recruitment/form.html", {"form": form, "title": "Post Freelance Project"})


def project_detail(request, pk):
    from recruitment.models import Project
    proj = get_object_or_404(Project, pk=pk)
    return render(request, "recruitment/project_detail.html", {"project": proj})


@login_required
@freelancer_required
def project_apply(request, pk):
    from recruitment.models import Project, ProjectProposal
    from recruitment.forms import ProjectProposalForm
    proj = get_object_or_404(Project, pk=pk, is_active=True)
    form = ProjectProposalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        prop = form.save(commit=False)
        prop.project = proj
        prop.freelancer = request.user
        prop.save()
        messages.success(request, f"Proposal submitted successfully for '{proj.title}'.")
        return redirect("freelancer_dashboard")
    return render(request, "recruitment/project_apply.html", {"form": form, "project": proj})


# ==============================================================================
# 9. NEWS & ANNOUNCEMENTS BROADCAST ENGINE VIEWS
# ==============================================================================

def news_list(request):
    """
    Public News & Circulars Hub.
    Displays platform broadcasts and company announcements visible to current user.
    """
    category = request.GET.get("category", "").strip()
    audience = request.GET.get("audience", "").strip()
    q = request.GET.get("q", "").strip()

    news_qs = NewsAnnouncement.objects.filter(is_active=True).select_related("author", "organization")

    if category:
        news_qs = news_qs.filter(category=category)
    if audience:
        news_qs = news_qs.filter(target_audience=audience)
    if q:
        news_qs = news_qs.filter(
            Q(title__icontains=q) |
            Q(summary__icontains=q) |
            Q(content__icontains=q) |
            Q(organization__name__icontains=q)
        )

    # Filter by user role visibility
    announcements = [n for n in news_qs if n.is_visible_to(request.user)]
    
    # Urgent alerts for banner
    urgent_alerts = [n for n in announcements if n.priority == NewsAnnouncement.Priority.URGENT and not n.is_expired][:3]

    return render(request, "recruitment/news_list.html", {
        "announcements": announcements,
        "urgent_alerts": urgent_alerts,
        "selected_category": category,
        "selected_audience": audience,
        "q": q,
        "categories": NewsAnnouncement.Category.choices,
        "audiences": NewsAnnouncement.TargetAudience.choices,
    })


def news_detail(request, slug):
    """Detail view for a single announcement."""
    announcement = get_object_or_404(NewsAnnouncement, slug=slug, is_active=True)
    if not announcement.is_visible_to(request.user):
        messages.error(request, "You do not have permission to view this announcement.")
        return redirect("news_list")

    # Increment view count
    NewsAnnouncement.objects.filter(pk=announcement.pk).update(views_count=F("views_count") + 1)
    announcement.views_count += 1

    related_news = NewsAnnouncement.objects.filter(
        is_active=True, category=announcement.category
    ).exclude(pk=announcement.pk).select_related("organization")[:4]

    return render(request, "recruitment/news_detail.html", {
        "announcement": announcement,
        "related_news": related_news,
    })


@login_required
def news_create(request):
    """
    Create announcement:
    - Platform Owner creates platform-wide or campus announcements.
    - Company Admin creates company hiring announcements.
    """
    if not (request.user.is_owner or request.user.is_company_admin):
        raise PermissionDenied("Only Platform Owners or Company Admins can publish announcements.")

    org = get_user_org(request.user) if not request.user.is_owner else None
    
    form = NewsAnnouncementForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        news = form.save(commit=False)
        news.author = request.user
        if not request.user.is_owner:
            news.organization = org
        else:
            org_id = request.POST.get("organization_id")
            if org_id:
                news.organization = Organization.objects.filter(id=org_id).first()
        news.save()
        log_audit(
            request, "NEWS_CREATED", "NewsAnnouncement", news.id,
            news.organization.id if news.organization else None,
            news.organization.name if news.organization else "Platform",
            {"title": news.title, "category": news.category}
        )
        messages.success(request, f"Announcement '{news.title}' published successfully.")
        return redirect("news_list")

    return render(request, "recruitment/news_form.html", {
        "form": form,
        "title": "Publish New Announcement or Notice",
        "organizations": Organization.objects.filter(is_active=True) if request.user.is_owner else None,
    })


@login_required
def news_edit(request, pk):
    """Edit announcement with role-based checks."""
    news = get_object_or_404(NewsAnnouncement, pk=pk)
    org = get_user_org(request.user)

    can_edit = (
        request.user.is_owner or
        news.author == request.user or
        (org and news.organization == org and request.user.is_company_admin)
    )
    if not can_edit:
        raise PermissionDenied("Permission denied.")

    form = NewsAnnouncementForm(request.POST or None, request.FILES or None, instance=news)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_audit(request, "NEWS_UPDATED", "NewsAnnouncement", news.id, details={"title": news.title})
        messages.success(request, f"Announcement '{news.title}' updated.")
        return redirect("news_detail", slug=news.slug)

    return render(request, "recruitment/news_form.html", {
        "form": form,
        "title": f"Edit Announcement: {news.title}",
        "news": news,
    })


@login_required
@require_POST
def news_delete(request, pk):
    """Delete announcement."""
    news = get_object_or_404(NewsAnnouncement, pk=pk)
    org = get_user_org(request.user)

    can_delete = (
        request.user.is_owner or
        news.author == request.user or
        (org and news.organization == org and request.user.is_company_admin)
    )
    if not can_delete:
        raise PermissionDenied("Permission denied.")

    news_title = news.title
    news.delete()
    log_audit(request, "NEWS_DELETED", "NewsAnnouncement", pk, details={"title": news_title})
    messages.success(request, f"Announcement '{news_title}' was deleted.")
    return redirect(request.META.get("HTTP_REFERER", "news_list"))


# ==============================================================================
# 11. STARTUP PLATFORM EXTENSIONS: COMPANIES, ANALYZER, RESOURCES & LEGAL
# ==============================================================================

def companies_list(request):
    """
    Public directory of verified hiring companies.
    Displays company branding, industry, location, and open vacancies count.
    """
    q = request.GET.get("q", "").strip()
    industry = request.GET.get("industry", "").strip()

    orgs = Organization.objects.filter(is_active=True).annotate(
        active_jobs_count=Count("jobs", filter=Q(jobs__is_active=True))
    ).order_by("-active_jobs_count", "name")

    if q:
        orgs = orgs.filter(Q(name__icontains=q) | Q(description__icontains=q) | Q(location__icontains=q))
    if industry:
        orgs = orgs.filter(industry__icontains=industry)

    total_companies = orgs.count()
    return render(request, "recruitment/companies_list.html", {
        "companies": orgs,
        "total_companies": total_companies,
        "q": q,
        "industry": industry,
    })


def resume_analyzer(request):
    """
    Public and Candidate AI Resume Screening & Diagnostic Engine.
    Uploads PDF/DOCX, extracts competencies, and benchmarks against industry target roles.
    """
    SAMPLE_TARGET_ROLES = {
        "Full Stack Developer (MCA / IT)": {
            "skills": ["Python", "Django", "JavaScript", "React", "SQL", "Git", "REST API", "Docker"],
            "dept": "MCA / Computer Applications",
            "desc": "Architect and build full-stack web applications using Python, Django, React, and relational databases.",
        },
        "Python / Django Backend Engineer": {
            "skills": ["Python", "Django", "PostgreSQL", "Redis", "Docker", "REST API", "Celery", "Linux"],
            "dept": "MCA / Engineering",
            "desc": "Design high-performance APIs, asynchronous task pipelines, and scalable backend microservices.",
        },
        "Data Analyst & BI Specialist": {
            "skills": ["Python", "SQL", "Pandas", "Power BI", "Tableau", "Business Analytics", "Data Visualization"],
            "dept": "MCA / MBA Analytics",
            "desc": "Extract business insights from relational databases, design executive BI dashboards, and automate reporting.",
        },
        "HR Manager & Talent Acquisition (MBA)": {
            "skills": ["Human Resources", "Talent Acquisition", "Employee Relations", "Performance Management", "Payroll"],
            "dept": "MBA / Human Resources",
            "desc": "Lead campus talent drives, manage employee lifecycle, ensure labor compliance, and streamline hiring.",
        },
        "Digital Marketing & Growth Manager (MBA)": {
            "skills": ["Digital Marketing", "SEO", "Google Ads", "Content Marketing", "Market Research", "Social Media"],
            "dept": "MBA / Marketing",
            "desc": "Formulate omnichannel marketing campaigns, optimize acquisition funnels, and scale inbound lead generation.",
        },
        "Software Engineer (B.Tech / B.E.)": {
            "skills": ["Java", "C++", "Data Structures", "Algorithms", "System Design", "SQL", "Git"],
            "dept": "Engineering",
            "desc": "Core engineering software development, algorithms, system design, and distributed applications.",
        },
    }

    analysis_result = None
    selected_role_key = request.POST.get("target_role", "Full Stack Developer (MCA / IT)")

    if request.method == "POST" and request.FILES.get("resume_file"):
        uploaded_file = request.FILES["resume_file"]
        is_valid, err_msg, mime_type, file_hash = validate_resume_file(uploaded_file)
        if not is_valid:
            messages.error(request, err_msg)
        else:
            try:
                # Save temporarily for extraction
                temp_filename = f"temp_analyzer_{file_hash[:8]}_{uploaded_file.name}"
                temp_path = Path(settings.MEDIA_ROOT) / "temp" / temp_filename
                temp_path.parent.mkdir(parents=True, exist_ok=True)
                with open(temp_path, "wb+") as destination:
                    for chunk in uploaded_file.chunks():
                        destination.write(chunk)

                raw_text = extract_resume_text(temp_path)
                if not raw_text.strip():
                    raise ValueError("Could not extract legible text. Scanned or image-only PDFs require OCR.")

                extracted_skills = extract_skills(raw_text)
                extracted_edu = extract_education(raw_text)
                extracted_exp = extract_experience_years(raw_text)

                target_spec = SAMPLE_TARGET_ROLES.get(selected_role_key, SAMPLE_TARGET_ROLES["Full Stack Developer (MCA / IT)"])
                target_skills = target_spec["skills"]
                target_desc = target_spec["desc"]

                match_data = calculate_match(raw_text, target_skills, target_desc)

                analysis_result = {
                    "file_name": uploaded_file.name,
                    "extracted_skills": extracted_skills,
                    "extracted_education": extracted_edu,
                    "experience_years": extracted_exp,
                    "target_role": selected_role_key,
                    "matched_skills": match_data["matched"],
                    "missing_skills": match_data["missing"],
                    "skill_score": match_data["skill_score"],
                    "semantic_score": match_data["semantic_score"],
                    "final_score": match_data["final_score"],
                    "explanation": match_data["explanation"],
                    "recommendation": match_data["recommendation"],
                    "text_preview": raw_text[:500] + ("..." if len(raw_text) > 500 else ""),
                }
                # Clean up temporary file
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass

                messages.success(request, f"AI Analysis Complete! Overall Match: {match_data['final_score']}%.")
            except Exception as e:
                messages.error(request, f"Analysis error: {e}")

    return render(request, "recruitment/resume_analyzer.html", {
        "analysis": analysis_result,
        "sample_roles": SAMPLE_TARGET_ROLES,
        "selected_role": selected_role_key,
    })


def career_resources(request):
    """Educational career hub with placement interview prep, salary benchmarks, and guides."""
    return render(request, "recruitment/career_resources.html")


def terms_view(request):
    """Platform Terms of Service."""
    return render(request, "recruitment/terms.html")


def privacy_view(request):
    """Platform Privacy Policy & Data Consent Information."""
    return render(request, "recruitment/privacy.html")


# ==============================================================================
# 12. CANDIDATE RESUME ACTIONS & SAVED JOBS
# ==============================================================================

@login_required
def preview_resume(request, pk):
    """
    Inline preview of verified resume in browser.
    Validates candidate ownership or authorized recruiter access.
    """
    resume = get_object_or_404(Resume, pk=pk)
    user = request.user

    is_owner = user.is_superuser or user.role == User.Role.OWNER
    is_author = resume.candidate_id == user.id

    is_authorized_hr = False
    if user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN]:
        org = get_user_org(user)
        if org:
            is_authorized_hr = Application.objects.filter(resume=resume, job__organization=org).exists()
        else:
            is_authorized_hr = Application.objects.filter(resume=resume, job__recruiter=user).exists()

    if not (is_owner or is_author or is_authorized_hr):
        raise PermissionDenied("You do not have authorization to view this resume.")

    try:
        response = FileResponse(resume.file.open("rb"), as_attachment=False, content_type=resume.mime_type or "application/pdf")
        response["Content-Disposition"] = f'inline; filename="{resume.file_name or "resume.pdf"}"'
        return response
    except FileNotFoundError:
        raise Http404("Resume document not found.")


@login_required
@candidate_required
@require_POST
def delete_resume(request, pk):
    """Candidate deletes a resume file from their profile."""
    resume = get_object_or_404(Resume, pk=pk, candidate=request.user)

    # Check if tied to an active pending application
    active_apps = Application.objects.filter(
        resume=resume,
        status__in=[Application.Status.APPLIED, Application.Status.SCREENING, Application.Status.SHORTLISTED, Application.Status.INTERVIEW]
    )
    if active_apps.exists():
        messages.error(request, "Cannot delete resume actively associated with an ongoing job application. Please withdraw your application first.")
        return redirect("candidate_dashboard")

    file_name = resume.file_name
    resume.delete()
    log_audit(request, "RESUME_DELETED", "Resume", pk, details={"file_name": file_name})
    messages.success(request, f"Resume '{file_name}' deleted successfully.")
    return redirect("candidate_dashboard")


@login_required
@candidate_required
@require_POST
def toggle_save_job(request, pk):
    """Candidate bookmarks or un-bookmarks a job opportunity."""
    job = get_object_or_404(Job, pk=pk, is_active=True)
    saved = SavedJob.objects.filter(candidate=request.user, job=job).first()

    if saved:
        saved.delete()
        is_saved = False
        msg = f"Job '{job.title}' removed from saved jobs."
    else:
        SavedJob.objects.create(candidate=request.user, job=job)
        is_saved = True
        msg = f"Job '{job.title}' saved to your bookmarks."

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": True, "saved": is_saved, "message": msg})

    messages.success(request, msg)
    return redirect(request.META.get("HTTP_REFERER", "job_list"))


@login_required
@candidate_required
def candidate_saved_jobs(request):
    """View all bookmarked jobs for the logged-in candidate."""
    saved_items = SavedJob.objects.filter(candidate=request.user).select_related("job", "job__organization").order_by("-saved_at")
    return render(request, "recruitment/saved_jobs.html", {"saved_items": saved_items})


@login_required
@candidate_required
def candidate_recommended_jobs(request):
    """Personalized AI job recommendations for the candidate based on profile skills & course."""
    profile, _ = CandidateProfile.objects.get_or_create(user=request.user)
    candidate_skills = [s.strip().lower() for s in profile.skills.split(",") if s.strip()]

    all_jobs = Job.objects.filter(is_active=True).select_related("organization")

    recommended = []
    for job in all_jobs:
        job_skills = job.skill_list()
        overlap = set(candidate_skills).intersection(set(job_skills))
        score = round((len(overlap) / len(job_skills) * 100), 1) if job_skills else 50.0

        # Course boost
        if profile.education and job.target_course != "ALL":
            if job.target_course.lower() in profile.education.lower():
                score = min(100.0, score + 15.0)

        if score >= 40.0:
            recommended.append({
                "job": job,
                "score": score,
                "overlap_skills": sorted(overlap),
                "missing_skills": sorted(set(job_skills) - set(candidate_skills)),
            })

    recommended.sort(key=lambda x: x["score"], reverse=True)

    return render(request, "recruitment/recommended_jobs.html", {
        "recommendations": recommended[:12],
        "profile": profile,
    })


@login_required
@candidate_required
@require_POST
def withdraw_application(request, pk):
    """Candidate voluntarily withdraws an application before final hiring."""
    app = get_object_or_404(Application, pk=pk, candidate=request.user)
    if app.status in [Application.Status.HIRED, Application.Status.REJECTED]:
        messages.error(request, "Cannot withdraw an application that has already concluded.")
        return redirect("candidate_dashboard")

    app.status = Application.Status.WITHDRAWN
    app.save(update_fields=["status"])

    # Notify recruiter
    Notification.objects.create(
        recipient=app.job.recruiter,
        sender=request.user,
        title=f"Application Withdrawn: {app.candidate.username}",
        message=f"{app.candidate.username} withdrew their application for {app.job.title}.",
        notification_type=Notification.Type.STATUS_UPDATE,
        link=f"/jobs/{app.job_id}/applicants/"
    )

    log_audit(request, "APPLICATION_WITHDRAWN", "Application", app.id, app.job.organization_id, app.job.company_name)
    messages.success(request, f"You have withdrawn your application for {app.job.title}.")
    return redirect("candidate_dashboard")


@login_required
@require_POST
def report_listing(request):
    """User reports suspicious job or project listing for administrator moderation."""
    target_id = request.POST.get("target_id", "").strip()
    target_title = request.POST.get("target_title", "").strip()
    report_type = request.POST.get("report_type", UserReport.ReportType.JOB_LISTING)
    reason = request.POST.get("reason", "").strip()

    if not reason or not target_id:
        messages.error(request, "Please provide the reason for reporting this listing.")
        return redirect(request.META.get("HTTP_REFERER", "home"))

    report = UserReport.objects.create(
        reporter=request.user,
        report_type=report_type,
        target_id=target_id,
        target_title=target_title,
        reason=reason,
    )
    log_audit(request, "LISTING_REPORTED", "UserReport", report.id, details={"target_id": target_id, "type": report_type})
    messages.success(request, "Thank you. Your report has been submitted for platform safety moderation.")
    return redirect(request.META.get("HTTP_REFERER", "home"))


# ==============================================================================
# 13. COMPANY VERIFICATION UPLOAD & NOTIFICATIONS
# ==============================================================================

@login_required
@company_admin_required
def company_verification_upload(request):
    """Company admin uploads compliance/incorporation documents for admin verification."""
    org = get_user_org(request.user)
    if not org:
        raise PermissionDenied("Organization not found.")

    if request.method == "POST" and request.FILES.get("doc_file"):
        doc_type = request.POST.get("document_type", "Certificate of Incorporation").strip()
        doc_file = request.FILES["doc_file"]

        CompanyVerificationDocument.objects.create(
            organization=org,
            document_type=doc_type,
            file=doc_file,
            submitted_by=request.user,
            status=CompanyVerificationDocument.Status.PENDING
        )
        # Update organization status to PENDING review if unverified
        if org.verification_status != Organization.VerificationStatus.APPROVED:
            org.verification_status = Organization.VerificationStatus.PENDING
            org.save(update_fields=["verification_status"])

        log_audit(request, "COMPANY_VERIFICATION_DOC_SUBMITTED", "CompanyVerificationDocument", org.id, org.id, org.name, {"document_type": doc_type})
        messages.success(request, f"Document '{doc_type}' submitted. Platform administrators will review your credentials.")
        return redirect("company_dashboard")

    docs = CompanyVerificationDocument.objects.filter(organization=org).order_by("-submitted_at")
    return render(request, "recruitment/company_verification.html", {"org": org, "documents": docs})


@login_required
def notifications_view(request):
    """User in-app notifications center with filtering and pagination."""
    notifications = Notification.objects.filter(recipient=request.user).order_by("-created_at")
    unread_count = notifications.filter(is_read=False).count()
    return render(request, "recruitment/notifications.html", {
        "notifications": notifications,
        "unread_count": unread_count,
    })


@login_required
@require_POST
def mark_all_notifications_read(request):
    """Marks all pending notifications as read."""
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": True})
    messages.success(request, "All notifications marked as read.")
    return redirect(request.META.get("HTTP_REFERER", "notifications_view"))


# ==============================================================================
# Hirenexa 2.0 Editorial & Discovery Suite: More Menu & Career Hub Views
# ==============================================================================

def about_view(request):
    """Comprehensive editorial About page for HireNexa 2.0 multi-tenant platform."""
    return render(request, "recruitment/about.html")


def contact_view(request):
    """Contact & support desk with headquarters information and verified CSRF messaging."""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        subject = request.POST.get("subject", "").strip()
        message_text = request.POST.get("message", "").strip()
        
        if name and email and message_text:
            messages.success(request, f"Thank you, {name}! Your message has been routed to HireNexa support.")
            return redirect("contact")
        else:
            messages.error(request, "Please complete all required fields before submitting.")
            
    return render(request, "recruitment/contact.html")


def career_guidance_view(request):
    """Structured engineering and product career roadmaps."""
    return render(request, "recruitment/career_guidance.html")


def interview_prep_view(request):
    """Interactive technical and behavioral interview preparation suite."""
    return render(request, "recruitment/interview_prep.html")


def resume_builder_view(request):
    """ATS-compliant resume studio with real-time preview and export options."""
    return render(request, "recruitment/resume_builder.html")


def salary_insights_view(request):
    """Pan-India compensation benchmarks and role percentile calculator."""
    return render(request, "recruitment/salary_insights.html")


def help_center_view(request):
    """Centralized help documentation and knowledge base categories."""
    return render(request, "recruitment/help_center.html")


def faq_view(request):
    """Comprehensive FAQ addressing candidates, recruiters, and platform governance."""
    return render(request, "recruitment/faq.html")


def pricing_view(request):
    """HireNexa Premium Subscription tiers and enterprise recruitment plans."""
    plans = SubscriptionPlan.objects.filter(is_active=True).order_by("price_monthly")
    return render(request, "recruitment/pricing.html", {"plans": plans})




