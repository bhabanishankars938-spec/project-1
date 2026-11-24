import time
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from .models import AuditLog, PlatformSetting


def get_client_ip(request):
    """Extract client IP from request headers."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


class SessionTimeoutMiddleware:
    """
    Monitors user activity and enforces session expiration.
    When idle time exceeds the configured threshold, securely logs the user out,
    creates an audit log entry, and redirects to login with an informational notice.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Attach client IP helper
        request.client_ip = get_client_ip(request)

        if request.user.is_authenticated:
            current_time = time.time()
            last_activity = request.session.get("_last_activity")

            # Configurable timeout in minutes from PlatformSetting or settings
            try:
                timeout_minutes = int(
                    PlatformSetting.get_value("SESSION_TIMEOUT_MINUTES", "240")
                )
            except (ValueError, TypeError):
                timeout_minutes = 240

            timeout_seconds = timeout_minutes * 60

            if last_activity and (current_time - last_activity > timeout_seconds):
                user = request.user
                AuditLog.objects.create(
                    user=user,
                    action="SESSION_EXPIRED",
                    ip_address=request.client_ip,
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                    details={"reason": "Inactivity timeout", "idle_seconds": int(current_time - last_activity)},
                )
                logout(request)
                messages.warning(
                    request,
                    "Your session has expired due to inactivity. Please sign in again to continue.",
                )
                return redirect("login")

            request.session["_last_activity"] = current_time

        response = self.get_response(request)
        return response
