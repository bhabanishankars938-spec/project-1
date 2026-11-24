from django.core.cache import cache
from django.urls import reverse
from accounts.models import User, PlatformSetting
from recruitment.models import Job, Notification, OrganizationMember, FreelancerProfile


def get_cached_job_count():
    count = cache.get("hirenexa_total_jobs_count")
    if count is None:
        try:
            count = Job.objects.filter(status="ACTIVE").count()
            if count == 0:
                count = Job.objects.count()
        except Exception:
            count = 0
        cache.set("hirenexa_total_jobs_count", count, timeout=60)
    return count


def get_cached_platform_settings():
    settings_dict = cache.get("platform_settings_all_dict")
    if settings_dict is None:
        try:
            items = PlatformSetting.objects.all()
            settings_dict = {item.key: item.value for item in items}
        except Exception:
            settings_dict = {}
        cache.set("platform_settings_all_dict", settings_dict, timeout=120)
    return settings_dict


def get_user_available_portals(user):
    """
    Returns the list of portals the authenticated user has legitimate access to.
    Platform Owner / Superadmin has universal access across all portals.
    Other users have access according to their primary role, org memberships, or secondary profiles.
    """
    portals = []

    # 1. Platform Owner / Super Admin
    if user.is_owner or user.is_superuser:
        portals.append({
            "role": "OWNER",
            "name": "Platform Owner",
            "icon": "🛡️",
            "desc": "Platform Governance & Admin Console",
            "url_name": "owner_dashboard",
            "color": "#fbbf24",
        })
        portals.append({
            "role": "COMPANY_ADMIN",
            "name": "Company Admin",
            "icon": "🏢",
            "desc": "Company Workspace & Team Seats",
            "url_name": "company_dashboard",
            "color": "#38bdf8",
        })
        portals.append({
            "role": "RECRUITER",
            "name": "HR Recruiter",
            "icon": "👥",
            "desc": "Talent Acquisition & Pipeline",
            "url_name": "hr_dashboard",
            "color": "#818cf8",
        })
        portals.append({
            "role": "FREELANCER",
            "name": "Freelancer",
            "icon": "💻",
            "desc": "Gigs, Contracts & Proposals",
            "url_name": "freelancer_dashboard",
            "color": "#38bdf8",
        })
        portals.append({
            "role": "CANDIDATE",
            "name": "Student / Candidate",
            "icon": "🎓",
            "desc": "Career Portal, Resumes & Jobs",
            "url_name": "candidate_dashboard",
            "color": "#34d399",
        })
        return portals

    # 2. Company Admin
    if user.is_company_admin:
        portals.append({
            "role": "COMPANY_ADMIN",
            "name": "Company Admin",
            "icon": "🏢",
            "desc": "Company Workspace & Team Seats",
            "url_name": "company_dashboard",
            "color": "#38bdf8",
        })
        portals.append({
            "role": "RECRUITER",
            "name": "HR Recruiter",
            "icon": "👥",
            "desc": "Talent Acquisition & Pipeline",
            "url_name": "hr_dashboard",
            "color": "#818cf8",
        })
        portals.append({
            "role": "CANDIDATE",
            "name": "Student / Candidate",
            "icon": "🎓",
            "desc": "Career Portal & Public Jobs",
            "url_name": "candidate_dashboard",
            "color": "#34d399",
        })
        return portals

    # 3. Recruiter
    if user.is_recruiter:
        portals.append({
            "role": "RECRUITER",
            "name": "HR Recruiter",
            "icon": "👥",
            "desc": "Talent Acquisition & Pipeline",
            "url_name": "hr_dashboard",
            "color": "#818cf8",
        })
        portals.append({
            "role": "CANDIDATE",
            "name": "Student / Candidate",
            "icon": "🎓",
            "desc": "Candidate Portal",
            "url_name": "candidate_dashboard",
            "color": "#34d399",
        })
        return portals

    # 4. Freelancer
    if user.is_freelancer:
        portals.append({
            "role": "FREELANCER",
            "name": "Freelancer",
            "icon": "💻",
            "desc": "Freelance Gigs & Proposals",
            "url_name": "freelancer_dashboard",
            "color": "#38bdf8",
        })
        portals.append({
            "role": "CANDIDATE",
            "name": "Student / Candidate",
            "icon": "🎓",
            "desc": "Job Seeker Career Portal",
            "url_name": "candidate_dashboard",
            "color": "#34d399",
        })
        return portals

    # 5. Candidate / Student (Default)
    portals.append({
        "role": "CANDIDATE",
        "name": "Student / Candidate",
        "icon": "🎓",
        "desc": "Career Portal, Resumes & Jobs",
        "url_name": "candidate_dashboard",
        "color": "#34d399",
    })

    # If Candidate has created a FreelancerProfile, also show Freelancer portal
    if FreelancerProfile.objects.filter(user=user).exists():
        portals.append({
            "role": "FREELANCER",
            "name": "Freelancer",
            "icon": "💻",
            "desc": "Freelance Gigs & Proposals",
            "url_name": "freelancer_dashboard",
            "color": "#38bdf8",
        })

    # If user has Organization memberships
    admin_org = OrganizationMember.objects.filter(user=user, role=OrganizationMember.MemberRole.ADMIN, is_active=True).first()
    if admin_org:
        portals.insert(0, {
            "role": "COMPANY_ADMIN",
            "name": "Company Admin",
            "icon": "🏢",
            "desc": f"{admin_org.organization.name} Workspace",
            "url_name": "company_dashboard",
            "color": "#38bdf8",
        })
    elif OrganizationMember.objects.filter(user=user, role=OrganizationMember.MemberRole.HR, is_active=True).exists():
        portals.insert(0, {
            "role": "RECRUITER",
            "name": "HR Recruiter",
            "icon": "👥",
            "desc": "Corporate Recruiting Portal",
            "url_name": "hr_dashboard",
            "color": "#818cf8",
        })

    return portals


def hirenexa_context(request):
    """
    Enterprise context processor for HireNexa:
    Supplies role awareness, available portals, notifications, job counts,
    and platform configuration globally to all templates.
    """
    total_jobs = get_cached_job_count()
    platform_settings = get_cached_platform_settings()

    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {
            "is_authenticated": False,
            "current_role": None,
            "current_role_display": "Guest",
            "current_role_badge_class": "guest",
            "available_portals": [],
            "unread_notifications_count": 0,
            "recent_notifications": [],
            "total_jobs": total_jobs,
            "total_jobs_count": total_jobs,
            "platform_settings": platform_settings,
            "can_post_vacancy": False,
            "can_post_notice": False,
            "can_post_gig": False,
            "can_upload_resume": False,
        }

    user = request.user

    # 1. Available portals
    available_portals = get_user_available_portals(user)
    portal_roles = [p["role"] for p in available_portals]

    # 2. Determine active role (from session or default user.role)
    session_role = request.session.get("active_role")
    if session_role and session_role in portal_roles:
        active_role = session_role
    elif user.role in portal_roles:
        active_role = user.role
    elif portal_roles:
        active_role = portal_roles[0]
    else:
        active_role = user.role

    # Mark active state in portals list
    for p in available_portals:
        p["is_active"] = (p["role"] == active_role)

    # 3. Role display names & badge classes
    role_display_map = {
        "OWNER": "Platform Owner",
        "COMPANY_ADMIN": "Company Admin",
        "RECRUITER": "HR Recruiter",
        "FREELANCER": "Freelancer",
        "CANDIDATE": "Student / Candidate",
    }
    badge_class_map = {
        "OWNER": "owner",
        "COMPANY_ADMIN": "company_admin",
        "RECRUITER": "recruiter",
        "FREELANCER": "freelancer",
        "CANDIDATE": "candidate",
    }

    # 4. Unread notifications & recent 5
    notif_cache_key = f"user_notif_unread_{user.id}"
    unread_count = cache.get(notif_cache_key)
    if unread_count is None:
        try:
            unread_count = Notification.objects.filter(recipient=user, is_read=False).count()
        except Exception:
            unread_count = 0
        cache.set(notif_cache_key, unread_count, timeout=30)

    try:
        recent_notifications = list(
            Notification.objects.filter(recipient=user)
            .select_related("sender")
            .order_by("-created_at")[:5]
        )
    except Exception:
        recent_notifications = []

    # 5. Role permissions for action buttons
    is_owner_or_admin = (user.is_owner or user.is_superuser or active_role == "OWNER")
    is_company_or_hr = (user.is_company_admin or user.is_recruiter or active_role in ["COMPANY_ADMIN", "RECRUITER"])
    is_freelance = (user.is_freelancer or active_role == "FREELANCER")
    is_cand = (user.is_candidate or active_role == "CANDIDATE")

    can_post_vacancy = is_owner_or_admin or is_company_or_hr
    can_post_notice = is_owner_or_admin
    can_post_gig = is_owner_or_admin or is_company_or_hr or is_freelance
    can_upload_resume = is_cand or is_owner_or_admin

    # 6. User Settings
    try:
        user_settings = user.settings
    except Exception:
        user_settings = None

    return {
        "is_authenticated": True,
        "current_role": active_role,
        "current_role_display": role_display_map.get(active_role, user.get_role_display()),
        "current_role_badge_class": badge_class_map.get(active_role, "candidate"),
        "available_portals": available_portals,
        "unread_notifications_count": unread_count,
        "recent_notifications": recent_notifications,
        "total_jobs": total_jobs,
        "total_jobs_count": total_jobs,
        "platform_settings": platform_settings,
        "user_settings": user_settings,
        "can_post_vacancy": can_post_vacancy,
        "can_post_notice": can_post_notice,
        "can_post_gig": can_post_gig,
        "can_upload_resume": can_upload_resume,
        "is_platform_owner_role": is_owner_or_admin,
    }
