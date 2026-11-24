from functools import wraps
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect
from .models import User, AuditLog


def get_client_ip(request):
    """Extract client IP from request headers."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def render_permission_denied(request, reason, required_role="Privileged Role"):
    """
    Renders the enterprise 403 Access Denied template with full contextual
    role switching buttons, active session metadata, and clear resolution actions.
    Maintains strict HTTP 403 status code for security compliance and test suites.
    """
    context = {
        "exception": reason,
        "path": request.path,
        "required_role": required_role,
    }
    return render(request, "403.html", context, status=403)


def owner_required(view_func):
    """
    Restricts access strictly to Platform Owners and Super Admins.
    Unauthorized attempts are logged to the Audit Trail and denied with 403.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")

        if not request.user.is_owner:
            AuditLog.objects.create(
                user=request.user,
                action="UNAUTHORIZED_OWNER_AREA_ACCESS_ATTEMPT",
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                details={"attempted_path": request.path, "user_role": request.user.role},
            )
            messages.error(
                request,
                "Access Denied: You do not possess Platform Owner or Super Admin privileges.",
            )
            return render_permission_denied(
                request,
                "Restricted to Platform Owner / Super Admin only.",
                required_role="Platform Owner"
            )
        return view_func(request, *args, **kwargs)
    return _wrapped


def company_admin_required(view_func):
    """Restricts access to Company Administrators and Platform Owners."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/company/login/?next={request.path}")
        if request.user.is_company_admin or request.user.is_owner:
            return view_func(request, *args, **kwargs)
        if request.user.is_recruiter:
            messages.info(request, "Redirected to your HR Recruiter Workspace.")
            return redirect("hr_dashboard")
        
        AuditLog.objects.create(
            user=request.user,
            action="UNAUTHORIZED_COMPANY_ADMIN_ACCESS_ATTEMPT",
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            details={"attempted_path": request.path, "user_role": request.user.role},
        )
        messages.error(
            request,
            "Access Denied: This workspace is restricted to Company Administrators.",
        )
        return render_permission_denied(
            request,
            "Company Admin privileges required. Please switch to a Company Administrator account or return to your dashboard.",
            required_role="Company Administrator"
        )
    return _wrapped


def recruiter_required(view_func):
    """Restricts access to HR / Recruiters, Company Admins, and Platform Owners."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")
        if not (request.user.is_recruiter or request.user.is_company_admin or request.user.is_owner):
            messages.error(
                request,
                "Access Denied: This workspace is restricted to HR / Recruiters.",
            )
            return render_permission_denied(
                request,
                "HR / Recruiter privileges required.",
                required_role="HR / Recruiter"
            )
        return view_func(request, *args, **kwargs)
    return _wrapped


def freelancer_required(view_func):
    """Restricts access to Freelancers and Platform Owners."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")
        if not (request.user.is_freelancer or request.user.is_owner):
            messages.error(
                request,
                "Access Denied: This workspace is restricted to Freelancers.",
            )
            return render_permission_denied(
                request,
                "Freelancer privileges required.",
                required_role="Freelancer"
            )
        return view_func(request, *args, **kwargs)
    return _wrapped


def candidate_required(view_func):
    """Restricts access to Candidates / Students and Platform Owners."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")
        if not (request.user.is_candidate or request.user.is_owner):
            messages.error(
                request,
                "Access Denied: This portal is restricted to Students & Candidates.",
            )
            return render_permission_denied(
                request,
                "Candidate privileges required.",
                required_role="Student / Candidate"
            )
        return view_func(request, *args, **kwargs)
    return _wrapped
