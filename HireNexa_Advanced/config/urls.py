from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from rest_framework.routers import DefaultRouter
from accounts import views as accounts_views
from recruitment.api_views import (
    OrganizationViewSet, JobViewSet, ApplicationViewSet,
    InterviewViewSet, AuditLogViewSet, owner_analytics_api, openapi_schema_view
)


def robots_txt(request):
    """SEO & Privacy guard: Prevent crawling private meeting rooms, video streams, and interview notes while indexing public webinars, jobs, and articles."""
    content = (
        "User-agent: *\n"
        "Disallow: /connect/room/\n"
        "Disallow: /connect/studio/\n"
        "Disallow: /connect/api/\n"
        "Disallow: /assessments/take/\n"
        "Disallow: /owner/\n"
        "Disallow: /hr/\n"
        "Disallow: /company/\n"
        "Disallow: /candidate/\n"
        "Disallow: /freelancer/\n"
        "Disallow: /api/\n"
        "Allow: /connect/events/\n"
        "Allow: /jobs/\n"
        "Allow: /companies/\n"
        "Allow: /news/\n"
        "Allow: /pricing/\n"
        "Allow: /resources/\n"
        "Allow: /$\n\n"
        "Sitemap: https://hirenexa.com/sitemap.xml\n"
    )
    return HttpResponse(content, content_type="text/plain; charset=utf-8")


router = DefaultRouter()
router.register(r"organizations", OrganizationViewSet, basename="api_organization")
router.register(r"jobs", JobViewSet, basename="api_job")
router.register(r"applications", ApplicationViewSet, basename="api_application")
router.register(r"interviews", InterviewViewSet, basename="api_interview")
router.register(r"audit-logs", AuditLogViewSet, basename="api_audit_log")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("robots.txt", robots_txt, name="robots_txt"),

    # Phase 2: Top-Level Four Portal Vanity Login Routes
    path("owner/login/", accounts_views.owner_login_view, name="vanity_owner_login"),
    path("owner/setup/", accounts_views.first_time_owner_setup_view, name="vanity_owner_setup"),
    path("company/login/", accounts_views.hr_login_view, name="vanity_company_login"),
    path("hr/login/", accounts_views.hr_login_view, name="vanity_hr_login"),
    path("candidate/login/", accounts_views.candidate_login_view, name="vanity_candidate_login"),
    path("student/login/", accounts_views.candidate_login_view, name="vanity_student_login"),
    path("freelancer/login/", accounts_views.freelancer_login_view, name="vanity_freelancer_login"),
    path("roles/", accounts_views.role_hub_view, name="vanity_roles_hub"),
    path("demo/switch/<str:role>/", accounts_views.demo_login_view, name="demo_switch_role"),

    path("connect/", include("connect.urls")),
    path("", include("recruitment.urls")),
    path("assessments/", include("assessments.urls")),
    path("accounts/", include("accounts.urls")),
    path("settings/", include("accounts.urls_settings")),
    path("ai/", include("ai_assistant.urls")),
    path("assistant/", include("ai_assistant.urls")),
    
    # REST API Endpoints
    path("api/v1/", include(router.urls)),
    path("api/v1/owner/analytics/", owner_analytics_api, name="api_owner_analytics"),
    path("api/v1/openapi/", openapi_schema_view, name="openapi-schema"),
]

handler403 = "accounts.views.custom_403_view"
handler404 = "accounts.views.custom_404_view"
handler500 = "accounts.views.custom_500_view"
