import re
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth import authenticate, login
from django.utils import timezone
from accounts.models import User, AuditLog
from accounts.utils import log_audit
from .models import (
    Organization, OrganizationMember, Job, Resume, Application,
    AIMatchResult, Interview, Notification, ShortlistedCandidate,
    Country, State, District, City, Area, PinCode,
    ProjectPortfolio, ProjectFile
)
from .serializers import (
    UserSerializer, OrganizationSerializer, JobSerializer, ApplicationSerializer,
    InterviewSerializer, ResumeSerializer, AuditLogSerializer
)


class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and (request.user.role == User.Role.OWNER or request.user.is_superuser)


class IsPlatformOwnerOrOrgAdmin(permissions.BasePermission):
    """
    Enforces strict multi-tenant RBAC on Organization models:
    - Safe methods (GET, HEAD, OPTIONS): Public read access.
    - Create: Restricted to Platform Owner, Superuser, or registered Company Admins/Recruiters.
    - Update/Partial Update/Destroy: Restricted to Platform Owner, Superuser,
      or active ADMIN members of that specific Organization.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser or request.user.role == User.Role.OWNER:
            return True
        if view.action == "create":
            return request.user.role in [User.Role.COMPANY_ADMIN, User.Role.RECRUITER]
        return request.user.role in [User.Role.COMPANY_ADMIN, User.Role.OWNER]

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser or request.user.role == User.Role.OWNER:
            return True
        return OrganizationMember.objects.filter(
            organization=obj,
            user=request.user,
            role=OrganizationMember.MemberRole.ADMIN,
            is_active=True,
        ).exists()


class IsJobRecruiterOrOrgAdmin(permissions.BasePermission):
    """
    Enforces strict multi-tenant RBAC on Job postings:
    - Safe methods: Read access (scoped by get_queryset).
    - Create: Platform Owner, Company Admin, or Recruiter.
    - Update/Destroy: Platform Owner, assigned job recruiter, or Company Admin of that job's organization.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser or request.user.role == User.Role.OWNER:
            return True
        return request.user.role in [User.Role.COMPANY_ADMIN, User.Role.RECRUITER]

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser or request.user.role == User.Role.OWNER:
            return True
        if obj.recruiter == request.user:
            return True
        if obj.organization:
            return OrganizationMember.objects.filter(
                organization=obj.organization,
                user=request.user,
                role=OrganizationMember.MemberRole.ADMIN,
                is_active=True,
            ).exists()
        return False


class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [IsPlatformOwnerOrOrgAdmin]


class JobViewSet(viewsets.ModelViewSet):
    serializer_class = JobSerializer
    permission_classes = [IsJobRecruiterOrOrgAdmin]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Job.objects.filter(is_active=True)
        if user.role == User.Role.OWNER or user.is_superuser:
            return Job.objects.all()
        if user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN]:
            org_member = OrganizationMember.objects.filter(user=user, is_active=True).first()
            if org_member:
                return Job.objects.filter(organization=org_member.organization)
            return Job.objects.filter(recruiter=user)
        return Job.objects.filter(is_active=True)

    def perform_create(self, serializer):
        user = self.request.user
        org_member = OrganizationMember.objects.filter(user=user, is_active=True).first()
        org = org_member.organization if org_member else None
        job = serializer.save(
            recruiter=user,
            organization=org,
            company_name=org.name if org else (user.username)
        )
        log_audit(self.request, "API_JOB_CREATED", "Job", job.id, org.id if org else None, job.company_name)


class ApplicationViewSet(viewsets.ModelViewSet):
    serializer_class = ApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Application.objects.none()
        if user.role == User.Role.OWNER or user.is_superuser:
            return Application.objects.all()
        if user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN]:
            org_member = OrganizationMember.objects.filter(user=user, is_active=True).first()
            if org_member:
                return Application.objects.filter(job__organization=org_member.organization)
            return Application.objects.filter(job__recruiter=user)
        return Application.objects.filter(candidate=user)


class InterviewViewSet(viewsets.ModelViewSet):
    serializer_class = InterviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Interview.objects.none()
        if user.role == User.Role.OWNER or user.is_superuser:
            return Interview.objects.all()
        if user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN]:
            org_member = OrganizationMember.objects.filter(user=user, is_active=True).first()
            if org_member:
                return Interview.objects.filter(application__job__organization=org_member.organization)
            return Interview.objects.filter(application__job__recruiter=user)
        return Interview.objects.filter(application__candidate=user)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == User.Role.OWNER or user.is_superuser:
            return AuditLog.objects.all()
        return AuditLog.objects.filter(user=user)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def owner_analytics_api(request):
    """Platform Owner Master Analytics API endpoint."""
    user = request.user
    if not (user.role == User.Role.OWNER or user.is_superuser):
        return Response({"error": "Platform Owner access required"}, status=status.HTTP_403_FORBIDDEN)

    return Response({
        "status": "success",
        "timestamp": timezone.now().isoformat(),
        "kpis": {
            "total_candidates": User.objects.filter(role=User.Role.CANDIDATE).count(),
            "total_companies": Organization.objects.count(),
            "total_hr_users": User.objects.filter(role__in=[User.Role.RECRUITER, User.Role.COMPANY_ADMIN]).count(),
            "total_uploaded_resumes": Resume.objects.count(),
            "total_active_jobs": Job.objects.filter(is_active=True).count(),
            "total_applications": Application.objects.count(),
            "total_interviews": Interview.objects.count(),
            "total_shortlisted": ShortlistedCandidate.objects.count(),
            "total_ai_processed_resumes": AIMatchResult.objects.count(),
        }
    })


def openapi_schema_view(request):
    """OpenAPI 3.0 specification for HireNexa Enterprise API."""
    schema = {
        "openapi": "3.0.3",
        "info": {
            "title": "HireNexa Enterprise Recruitment & AI Matching API",
            "version": "2.0.0",
            "description": "Multi-tenant recruitment platform APIs for candidates, organizations, jobs, applications, AI resume screening, and audit logs."
        },
        "servers": [{"url": "/api/v1/"}],
        "paths": {
            "/organizations/": {
                "get": {"summary": "List verified organizations", "responses": {"200": {"description": "Array of organizations"}}},
                "post": {"summary": "Register new organization", "responses": {"201": {"description": "Organization created"}}}
            },
            "/jobs/": {
                "get": {"summary": "List active job postings", "responses": {"200": {"description": "Array of jobs"}}},
                "post": {"summary": "Post new job vacancy", "responses": {"201": {"description": "Job created"}}}
            },
            "/applications/": {
                "get": {"summary": "List candidate applications", "responses": {"200": {"description": "Applications list"}}},
                "post": {"summary": "Submit job application with AI scoring", "responses": {"201": {"description": "Application submitted"}}}
            },
            "/interviews/": {
                "get": {"summary": "List scheduled interviews", "responses": {"200": {"description": "Interview schedule"}}},
                "post": {"summary": "Schedule candidate interview round", "responses": {"201": {"description": "Interview scheduled"}}}
            },
            "/owner/analytics/": {
                "get": {"summary": "Platform Owner Central Intelligence KPIs", "responses": {"200": {"description": "Platform KPI metrics"}}}
            },
            "/audit-logs/": {
                "get": {"summary": "Security audit trail", "responses": {"200": {"description": "Array of audit logs"}}}
            },
            "/locations/autocomplete/": {
                "get": {"summary": "India location autocomplete and work mode selector", "responses": {"200": {"description": "Matching locations"}}}
            },
            "/locations/hierarchy/": {
                "get": {"summary": "Cascading Country-State-District-City-Area-PIN selector", "responses": {"200": {"description": "Hierarchy nodes"}}}
            }
        }
    }
    return JsonResponse(schema)


# ==============================================================================
# INDIA LOCATION MANAGEMENT & AUTOCOMPLETE APIS
# ==============================================================================

def search_india_locations(q, limit=15):
    """
    Intelligent multi-token, reversed-order, case-insensitive Indian location search.
    Resolves:
      - 'Deogarh'
      - 'Odisha Deogarh' / 'Deogarh Odisha' / 'Deogarh, Odisha'
      - 'Bhubaneswar' / 'Bhubaneswar Odisha' / 'Odisha Bhubaneswar'
      - 'Patia' / 'Patia Bhubaneswar'
      - 6-digit PIN codes (e.g. '768119')
      - Work modes: 'All India', 'Remote', 'Hybrid', 'On-site'
    """
    if not q or not q.strip():
        return []

    q_clean = q.strip()
    q_lower = q_clean.lower()
    results = []
    seen_keys = set()

    def add_result(res_dict):
        key = (res_dict.get("type"), res_dict.get("value", "").lower(), res_dict.get("label", "").lower())
        if key not in seen_keys:
            seen_keys.add(key)
            results.append(res_dict)

    # 1. Mode shortcuts
    if "all india".startswith(q_lower) or "pan india".startswith(q_lower) or q_lower in ["all", "india"]:
        add_result({
            "id": "mode_all",
            "label": "All India",
            "sublabel": "Pan-India Open Roles",
            "subtext": "Pan India / Anywhere in India",
            "badge": "PAN INDIA",
            "type": "mode",
            "value": "All India"
        })
    if "remote".startswith(q_lower) or "wfh".startswith(q_lower):
        add_result({
            "id": "mode_remote",
            "label": "Remote",
            "sublabel": "Work from Anywhere",
            "subtext": "Work from Anywhere (WFA)",
            "badge": "WORK MODE",
            "type": "mode",
            "value": "Remote"
        })
    if "hybrid".startswith(q_lower):
        add_result({
            "id": "mode_hybrid",
            "label": "Hybrid",
            "sublabel": "Flexible In-Office & Remote",
            "subtext": "Flexible On-site & Remote",
            "badge": "WORK MODE",
            "type": "mode",
            "value": "Hybrid"
        })
    if "on-site".startswith(q_lower) or "onsite".startswith(q_lower) or "office".startswith(q_lower):
        add_result({
            "id": "mode_onsite",
            "label": "On-site",
            "sublabel": "Office Location",
            "subtext": "In-office Presence",
            "badge": "WORK MODE",
            "type": "mode",
            "value": "On-site"
        })

    # 2. PIN Codes (Priority 1)
    if q_clean.isdigit():
        pins = PinCode.objects.filter(pin_code__startswith=q_clean).select_related("city", "state", "area", "district")[:8]
        for p in pins:
            loc_name = p.area.name if p.area else (p.city.name if p.city else (p.district.name if p.district else p.state.name))
            city_str = f"{p.city.name}, " if (p.city and p.city.name != loc_name) else ""
            dist_str = f"{p.district.name} District, " if (p.district and p.district.name != loc_name) else ""
            sub = f"{loc_name}, {city_str}{dist_str}{p.state.name}".replace(", ,", ", ").strip(", ")
            hierarchy_path = f"India > {p.state.name} > {p.district.name if p.district else (p.city.name if p.city else p.state.name)} > {p.city.name if p.city else loc_name} > {p.pin_code}"
            add_result({
                "id": f"pin_{p.id}",
                "label": f"{p.pin_code} - {loc_name}, {p.state.code}",
                "sublabel": p.office_name or sub,
                "subtext": sub,
                "badge": "PIN CODE",
                "type": "pin_code",
                "value": p.pin_code,
                "hierarchy": hierarchy_path,
                "priority": 1,
            })

    # 3. Known Administrative Aliases & Spelling Correction Map
    ADMIN_ALIASES = {
        "bhubneswar": "Bhubaneswar",
        "bhubaneshwar": "Bhubaneswar",
        "bbsr": "Bhubaneswar",
        "orissa": "Odisha",
        "odisa": "Odisha",
        "bangalore": "Bengaluru",
        "bengaluru": "Bengaluru",
        "bombay": "Mumbai",
        "mumbai": "Mumbai",
        "calcutta": "Kolkata",
        "kolkata": "Kolkata",
        "madras": "Chennai",
        "chennai": "Chennai",
        "poona": "Pune",
        "pune": "Pune",
        "gurgaon": "Gurugram",
        "gurugram": "Gurugram",
        "deogarh": "Deogarh",
        "debagarh": "Deogarh",
        "khurda": "Khordha",
        "khordha": "Khordha",
        "cuttack": "Cuttack",
        "kataka": "Cuttack",
        "sambalpur": "Sambalpur",
        "reamal": "Reamal",
        "barkote": "Barkote",
        "patia": "Patia",
        "chandrasekharpur": "Chandrasekharpur",
        "trivandrum": "Thiruvananthapuram",
        "cochin": "Kochi",
        "vizag": "Visakhapatnam",
        "baroda": "Vadodara",
        "mysore": "Mysuru",
        "mangalore": "Mangaluru",
    }

    # 4. Tokenize query for multi-word / reversed-word search
    raw_tokens = [re.sub(r'[^a-zA-Z0-9]', '', t).strip().lower() for t in re.split(r'[\s,/\->]+', q_clean)]
    tokens = [t for t in raw_tokens if t and t not in ['in', 'at', 'near', 'district', 'dist', 'state', 'city', 'india']]

    if not tokens:
        tokens = [q_lower]

    # Resolve each token to its canonical administrative name if an alias or typo exists
    import difflib
    resolved_tokens = []
    has_fuzzy_correction = False
    for tok in tokens:
        if tok in ADMIN_ALIASES:
            resolved_tokens.append(ADMIN_ALIASES[tok].lower())
            if tok != ADMIN_ALIASES[tok].lower():
                has_fuzzy_correction = True
        else:
            close_matches = difflib.get_close_matches(tok, list(ADMIN_ALIASES.keys()), n=1, cutoff=0.72)
            if close_matches:
                canonical = ADMIN_ALIASES[close_matches[0]].lower()
                resolved_tokens.append(canonical)
                has_fuzzy_correction = True
            else:
                resolved_tokens.append(tok)

    # Search tokens use the canonical resolved tokens
    search_tokens = resolved_tokens

    # --- Match Districts (Priority 3) ---
    dist_q = models.Q()
    for tok in search_tokens:
        dist_q &= (
            models.Q(name__icontains=tok) |
            models.Q(state__name__icontains=tok) |
            models.Q(state__code__iexact=tok)
        )
    for d in District.objects.filter(dist_q).select_related("state")[:8]:
        is_exact = d.name.lower() in [t.lower() for t in search_tokens]
        add_result({
            "id": f"district_{d.id}",
            "label": f"{d.name}, {d.name} District, {d.state.name}, India",
            "sublabel": f"{d.state.name} · District",
            "subtext": f"{d.name} District, {d.state.name}, India",
            "badge": "DISTRICT",
            "type": "district",
            "value": d.name,
            "hierarchy": f"India > {d.state.name} > {d.name}",
            "priority": 3 if is_exact else 4,
        })

    # --- Match Cities / Towns / Tehsils (Priority 2) ---
    city_q = models.Q()
    for tok in search_tokens:
        city_q &= (
            models.Q(name__icontains=tok) |
            models.Q(district__name__icontains=tok) |
            models.Q(state__name__icontains=tok) |
            models.Q(state__code__iexact=tok)
        )
    for c in City.objects.filter(city_q).select_related("state", "district")[:10]:
        dist_str = f"{c.district.name} District, " if c.district else ""
        is_exact = c.name.lower() in [t.lower() for t in search_tokens]
        add_result({
            "id": f"city_{c.id}",
            "label": f"{c.name}, {dist_str}{c.state.name}, India",
            "sublabel": "Metro Hub" if c.is_metro else f"Tier-{c.tier} City · {c.state.name}",
            "subtext": f"{c.name}, {c.state.name}, India",
            "badge": "METRO" if c.is_metro else "CITY",
            "type": "city",
            "value": c.name,
            "hierarchy": f"India > {c.state.name} > {c.district.name if c.district else c.name} > {c.name}",
            "priority": 2 if is_exact else 4,
        })

    # --- Match Areas / Localities / Blocks (Priority 2) ---
    area_q = models.Q()
    for tok in search_tokens:
        area_q &= (
            models.Q(name__icontains=tok) |
            models.Q(city__name__icontains=tok) |
            models.Q(city__district__name__icontains=tok) |
            models.Q(city__state__name__icontains=tok)
        )
    for a in Area.objects.filter(area_q).select_related("city", "city__state", "city__district")[:10]:
        dist_str = f"{a.city.district.name} District, " if a.city.district else ""
        is_exact = a.name.lower() in [t.lower() for t in search_tokens]
        add_result({
            "id": f"area_{a.id}",
            "label": f"{a.name}, {a.city.name}, {dist_str}{a.city.state.name}, India",
            "sublabel": f"Area in {a.city.name}, {a.city.state.code}",
            "subtext": f"{a.name}, {a.city.name}, {a.city.state.name}",
            "badge": "LOCALITY",
            "type": "area",
            "value": a.name,
            "hierarchy": f"India > {a.city.state.name} > {a.city.district.name if a.city.district else a.city.name} > {a.city.name} > {a.name}",
            "priority": 2 if is_exact else 4,
        })

    # --- Match States (Priority 4) ---
    if len(tokens) == 1:
        tok = search_tokens[0]
        for s in State.objects.filter(models.Q(name__icontains=tok) | models.Q(code__iexact=tok))[:6]:
            add_result({
                "id": f"state_{s.id}",
                "label": f"{s.name}, India",
                "sublabel": f"All locations in {s.name} ({s.code})",
                "subtext": f"State in India · {s.get_type_display()}",
                "badge": "STATE",
                "type": "state",
                "value": s.name,
                "hierarchy": f"India > {s.name}",
                "priority": 3 if s.name.lower() == tok.lower() else 5,
            })

    # Resilient OR fallback if combined token query produced fewer than 3 results
    if len(results) < 3 and len(search_tokens) > 1:
        for tok in search_tokens:
            if len(tok) < 3:
                continue
            for c in City.objects.filter(
                models.Q(name__icontains=tok) | models.Q(district__name__icontains=tok) | models.Q(state__name__icontains=tok)
            ).select_related("state", "district")[:6]:
                dist_str = f"{c.district.name} District, " if c.district else ""
                add_result({
                    "id": f"city_{c.id}",
                    "label": f"{c.name}, {dist_str}{c.state.name}, India",
                    "sublabel": "Metro Hub" if c.is_metro else f"Tier-{c.tier} City · {c.state.name}",
                    "subtext": f"{c.name}, {c.state.name}, India",
                    "badge": "METRO" if c.is_metro else "CITY",
                    "type": "city",
                    "value": c.name,
                    "hierarchy": f"India > {c.state.name} > {c.district.name if c.district else c.name} > {c.name}",
                    "priority": 6,
                })
            for d in District.objects.filter(
                models.Q(name__icontains=tok) | models.Q(state__name__icontains=tok)
            ).select_related("state")[:5]:
                add_result({
                    "id": f"district_{d.id}",
                    "label": f"{d.name}, {d.name} District, {d.state.name}, India",
                    "sublabel": f"{d.state.name} · District",
                    "subtext": f"{d.name} District, {d.state.name}, India",
                    "badge": "DISTRICT",
                    "type": "district",
                    "value": d.name,
                    "hierarchy": f"India > {d.state.name} > {d.name}",
                    "priority": 6,
                })

    # Sort results by intelligent priority ranking (1=PIN, 2=City/Area, 3=District/State, 4=Partial, 5=Loose)
    results.sort(key=lambda x: x.get("priority", 99))
    return results[:limit]


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def location_autocomplete_api(request):
    """
    Searchable location autocomplete matching:
    Country → State → District → City → Area → PIN Code
    Along with work modes: 'All India', 'Remote', 'Hybrid', 'On-site'.
    """
    q = request.GET.get("q", "").strip()
    if not q or len(q) < 1:
        # Return popular metro cities and modes as default quick picks
        metros = City.objects.filter(is_metro=True).select_related("state")[:8]
        results = [
            {"id": "mode_all", "label": "All India", "sublabel": "Pan-India Open Roles", "subtext": "Pan India / Anywhere", "badge": "PAN INDIA", "type": "mode", "value": "All India"},
            {"id": "mode_remote", "label": "Remote", "sublabel": "Work from Anywhere", "subtext": "Work from Anywhere (WFA)", "badge": "WORK MODE", "type": "mode", "value": "Remote"},
            {"id": "mode_hybrid", "label": "Hybrid", "sublabel": "Flexible In-Office & Remote", "subtext": "Flexible On-site & Remote", "badge": "WORK MODE", "type": "mode", "value": "Hybrid"},
            {"id": "mode_onsite", "label": "On-site", "sublabel": "Office Location", "subtext": "In-office Presence", "badge": "WORK MODE", "type": "mode", "value": "On-site"},
        ]
        for m in metros:
            results.append({
                "id": f"city_{m.id}",
                "label": f"{m.name}, {m.state.name}, India",
                "sublabel": "Metro Hub",
                "subtext": f"{m.state.name} · Metro Hub",
                "badge": "METRO",
                "type": "city",
                "value": f"{m.name}, {m.state.name}",
            })
        return Response({"results": results})

    results = search_india_locations(q, limit=15)
    return Response({"count": len(results), "results": results})


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def location_hierarchy_api(request):
    """
    Hierarchical location selector & search:
    Country → State → District → City → Area → PIN Code
    """
    level = request.GET.get("level", "").lower()
    q = request.GET.get("q", "").strip()

    # Search mode across full hierarchy
    if q or level == "search":
        search_query = q or request.GET.get("search", "").strip()
        results = []
        if search_query:
            results = search_india_locations(search_query, limit=15)
        return Response({"success": True, "count": len(results), "results": results})

    if not level or level in ["all", "tree", "overview"]:
        countries = Country.objects.all()
        states = State.objects.all().order_by("name")
        return Response({
            "success": True,
            "countries": [{"id": c.id, "name": c.name, "iso2": c.iso2} for c in countries],
            "states": [{"id": s.id, "name": s.name, "code": s.code, "type": s.type} for s in states]
        })

    elif level == "states":
        states = State.objects.all().order_by("name")
        data = [{"id": s.id, "name": s.name, "code": s.code, "type": s.type} for s in states]
        return Response({"success": True, "states": data})

    elif level == "districts":
        state_id = request.GET.get("state_id")
        state_name = request.GET.get("state_name")
        qs = District.objects.all()
        if state_id:
            qs = qs.filter(state_id=state_id)
        elif state_name:
            qs = qs.filter(state__name__iexact=state_name)
        data = [{"id": d.id, "name": d.name, "state_id": d.state_id} for d in qs.order_by("name")]
        return Response({"success": True, "districts": data})

    elif level == "cities":
        state_id = request.GET.get("state_id")
        state_name = request.GET.get("state_name")
        district_id = request.GET.get("district_id")
        district_name = request.GET.get("district_name")
        qs = City.objects.all()
        if state_id:
            qs = qs.filter(state_id=state_id)
        elif state_name:
            qs = qs.filter(state__name__iexact=state_name)
        if district_id:
            qs = qs.filter(district_id=district_id)
        elif district_name:
            qs = qs.filter(district__name__iexact=district_name)
        data = [
            {
                "id": c.id,
                "name": c.name,
                "is_metro": c.is_metro,
                "tier": c.tier,
                "state_id": c.state_id,
                "district_id": c.district_id
            }
            for c in qs.order_by("name")
        ]
        return Response({"success": True, "cities": data})

    elif level == "areas":
        city_id = request.GET.get("city_id")
        city_name = request.GET.get("city_name")
        qs = Area.objects.all()
        if city_id:
            qs = qs.filter(city_id=city_id)
        elif city_name:
            qs = qs.filter(city__name__iexact=city_name)
        data = [{"id": a.id, "name": a.name, "city_id": a.city_id} for a in qs.order_by("name")]
        return Response({"success": True, "areas": data})

    elif level == "pincodes":
        city_id = request.GET.get("city_id")
        area_id = request.GET.get("area_id")
        qs = PinCode.objects.all()
        if city_id:
            qs = qs.filter(city_id=city_id)
        if area_id:
            qs = qs.filter(area_id=area_id)
        data = [
            {"id": p.id, "pin_code": p.pin_code, "office_name": p.office_name, "city_id": p.city_id}
            for p in qs.order_by("pin_code")
        ]
        return Response({"success": True, "pin_codes": data})

    return Response({"error": f"Invalid level '{level}'"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def interview_signal_api(request, pk):
    """
    WebRTC Signaling and In-Meeting Message Exchange for HireNexa Meet.
    Supports:
    - POST: publish SDP offers, answers, ICE candidates, and real-time chat messages.
    - GET: poll for new signals published by peer participants.
    """
    from django.core.cache import cache
    import time

    interview = get_object_or_404(Interview, pk=pk)
    if interview.status in ["COMPLETED", "CANCELLED"]:
        return Response({
            "success": False,
            "error": "This interview has ended.",
            "meeting_ended": True
        }, status=status.HTTP_410_GONE)

    app = interview.application

    is_cand = (app.candidate == request.user)
    is_recruiter = (
        app.job.recruiter == request.user or
        request.user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN, User.Role.OWNER]
    )
    if not (is_cand or is_recruiter or request.user.is_superuser):
        return Response({"error": "Unauthorized access to interview room"}, status=status.HTTP_403_FORBIDDEN)

    cache_key = f"hnx_webrtc_signals_{pk}"
    signals = cache.get(cache_key) or []

    if request.method == "POST":
        signal_type = request.data.get("type", "message")
        payload = request.data.get("payload", {})
        sender_name = request.user.get_full_name() or request.user.username

        new_signal = {
            "id": len(signals) + 1,
            "sender": request.user.username,
            "sender_name": sender_name,
            "is_host": not is_cand,
            "type": signal_type,
            "payload": payload,
            "timestamp": time.time(),
        }
        signals.append(new_signal)
        cache.set(cache_key, signals[-150:], timeout=14400)
        return Response({"success": True, "signal_id": new_signal["id"]})

    # GET: Poll for signals
    since_id = int(request.GET.get("since", 0))
    exclude_self = request.GET.get("exclude_self", "true").lower() == "true"

    unseen = [
        s for s in signals
        if s["id"] > since_id and (not exclude_self or s["sender"] != request.user.username)
    ]

    # Active presence tracking
    presence_key = f"hnx_webrtc_presence_{pk}"
    presence = cache.get(presence_key) or {}
    presence[request.user.username] = {
        "name": request.user.get_full_name() or request.user.username,
        "role": "Candidate" if is_cand else "Interviewer",
        "is_host": not is_cand,
        "last_seen": time.time(),
    }
    active_presence = {
        u: data for u, data in presence.items() if time.time() - data["last_seen"] < 30
    }
    cache.set(presence_key, active_presence, timeout=14400)

    return Response({
        "success": True,
        "signals": unseen,
        "participants": list(active_presence.values()),
        "interview_status": interview.status,
    })


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def interview_feedback_api(request, pk):
    """
    Save interviewer live evaluation feedback, notes, and meeting status.
    """
    interview = get_object_or_404(Interview, pk=pk)
    app = interview.application
    is_recruiter = (
        app.job.recruiter == request.user or
        request.user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN, User.Role.OWNER]
    )
    if not (is_recruiter or request.user.is_superuser):
        return Response({"error": "Only interviewers can submit scorecards"}, status=status.HTTP_403_FORBIDDEN)

    notes = request.data.get("notes", "")
    new_status = request.data.get("status", "")

    if notes:
        existing = interview.interviewer_feedback or ""
        timestamp = timezone.now().strftime("%Y-%m-%d %H:%M")
        interview.interviewer_feedback = f"{existing}\n[{timestamp} by {request.user.username}]: {notes}".strip()

    if new_status and new_status in Interview.Status.values:
        interview.status = new_status

    interview.save(update_fields=["interviewer_feedback", "status"])
    return Response({
        "success": True,
        "message": "Evaluation feedback saved successfully.",
        "status": interview.status,
    })
