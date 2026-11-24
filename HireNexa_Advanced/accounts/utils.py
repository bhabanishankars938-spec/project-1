from accounts.models import AuditLog

def get_client_ip(request):
    """Extract client IP address from request headers."""
    if not request:
        return ""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def log_audit(request, action, resource_type="", resource_id="", organization_id=None, organization_name="", details=None):
    """
    Centralized security audit logger for compliance and accountability.
    Records every sensitive access, download, status change, and login.
    """
    try:
        user = getattr(request, "user", None)
        user_obj = user if (user and user.is_authenticated) else None
        ip = get_client_ip(request)
        ua = request.META.get("HTTP_USER_AGENT", "")[:250] if request else ""
        
        return AuditLog.objects.create(
            user=user_obj,
            organization_id=organization_id,
            organization_name=organization_name,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            ip_address=ip,
            user_agent=ua,
            details=details or {},
        )
    except Exception as e:
        # Prevent audit log failures from blocking operations
        return None


def mask_email(email):
    """
    Masks email address for privacy and security.
    Example: 'ilovemymaaandpababhabanishanka@gmail.com' -> 'i***@gmail.com'
    """
    if not email or "@" not in email:
        return "your email"
    local, domain = email.strip().split("@", 1)
    if len(local) <= 1:
        masked = local + "***"
    else:
        masked = local[0] + "***"
    return f"{masked}@{domain}"

