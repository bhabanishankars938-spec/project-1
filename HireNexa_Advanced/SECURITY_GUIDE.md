# HireNexa V3 Enterprise SaaS – Cybersecurity & Hardening Guide

## 1. Security Architecture & Threat Model
HireNexa is built with defensive-in-depth principles designed to protect candidate personal identifiable information (PII), proprietary corporate recruitment metrics, and platform financial transactions.

```
 [ Client Request ]
        │
        ▼
 [ Nginx SSL/TLS Termination (TLS 1.2 / 1.3) ]
        │
        ▼
 [ Django Security Middleware (HSTS, CSP, X-Frame-Options) ]
        │
        ▼
 [ CSRF Token Validation (Double Submit Cookie) ]
        │
        ▼
 [ Session Authentication & Argon2id Verification ]
        │
        ▼
 [ Server-Side 5-Role RBAC Authorization Decorators ]
        │
        ▼
 [ Multi-Tenant Organization Boundary Verification ]
        │
        ▼
 [ Business Logic & Parametric ORM Operations ]
```

---

## 2. Authentication & Credential Storage

### A. Argon2id Password Hashing
All user passwords are encrypted using memory-hard **Argon2id** (`django.contrib.auth.hashers.Argon2PasswordHasher`):
- Time Cost: 2 iterations
- Memory Cost: 102,400 KB (100 MB)
- Parallelism: 8 threads
- Salt: 16 cryptographically secure random bytes generated via `os.urandom`.

### B. Four Distinct Vanity Portals
Public registration strictly defaults to low-privilege roles (`CANDIDATE`, `COMPANY_ADMIN`, `FREELANCER`).
- **Owner Elevation Guard**: The Platform Owner (`OWNER` / Super Admin) can never be registered through public forms. Owner initialization is gated behind CLI command `python manage.py create_platform_owner`.
- **Role Tampering Prevention**: The user's role is never accepted from request parameters or hidden input fields. It is read directly from `request.user.role` from the authenticated database session.

---

## 3. Five-Tier Role-Based Access Control (RBAC)

| Role | Portal Route | Permitted Capabilities | Restrictions |
| :--- | :--- | :--- | :--- |
| **Platform Owner** | `/owner/` | Master administration, approve/reject companies, manage SaaS pricing plans, review audit logs, promote jobs. | Bound by data privacy audit logs. |
| **Company Admin** | `/company/` | Manage corporate workspace, invite/provision HR recruiter seats, manage billing and jobs. | Strictly isolated to own organization. Cannot access other firms. |
| **HR Recruiter** | `/hr/` | Post jobs via 6-step wizard, review applicants, evaluate AI matching, schedule interviews. | Cannot manage subscription plans or change company settings. |
| **Candidate** | `/candidate/` | Upload resumes, enrich education/skills/projects, track hiring pipeline, withdraw consent. | Only views own applications and public vacancies. |
| **Freelancer** | `/freelancer/` | Browse project requests, submit bids/proposals, manage hourly rates. | Cannot access corporate candidate pipelines. |

---

## 4. File Upload & Binary Malicious Code Protection

### A. Magic Byte Inspection
Files submitted to `/resumes/upload/` undergo 3-tier validation in `DataQualityAgent`:
1. **Extension Enforcement**: Only `.pdf` and `.docx` are accepted.
2. **Size Boundary**: Max file size is capped at 5 MB (5,242,880 bytes).
3. **Magic Byte Signature Verification**:
   - PDF files must begin with `%PDF-` bytes (`0x25 0x50 0x44 0x46 0x2D`).
   - DOCX files must start with PK ZIP signatures (`0x50 0x4B 0x03 0x04`).
   - Files disguising PE executables (`MZ`), shell scripts (`#!/`), or HTML/JS are rejected with a security exception.

### B. SHA-256 Cryptographic Tracking
Every uploaded document is hashed with SHA-256 upon ingestion:
- Prevents redundant disk storage through hash deduplication.
- Generates an immutable checksum for forensic integrity.

### C. Private Object Storage & Authorized Downloads
Resumes are stored outside public static directories. The endpoint `download_resume(request, pk)` enforces:
- Candidate can only download their own resumes.
- Recruiters can only download resumes of candidates who have applied to jobs belonging to their organization.
- Platform Owner has authorized compliance download access.

---

## 5. Countermeasures Against OWASP Top 10

### 1. Broken Access Control & IDOR
- Every database query for tenant resources checks `job.organization == get_user_org(request.user)`.
- Direct object reference tampering on `/jobs/<id>/delete/` or `/applicants/<id>/` raises `PermissionDenied` (HTTP 403).

### 2. Injection (SQLi & Command Injection)
- 100% of queries use Django ORM parameterization.
- No `cursor.execute("SELECT ... " + var)` or `eval()` constructs exist.

### 3. Cross-Site Scripting (XSS)
- Django template engine auto-escapes all context variables.
- Raw HTML fields utilize strict Markdown conversion without `|safe` on user-controlled inputs.

### 4. Cross-Site Request Forgery (CSRF)
- `CsrfViewMiddleware` is active on all POST/PUT/DELETE requests.
- State-changing actions enforce `@require_POST` with valid `{% csrf_token %}` cookies.

### 5. Security Misconfiguration & Clickjacking
- `X-Frame-Options: DENY` prevents framing inside malicious iframes.
- `SECURE_BROWSER_XSS_FILTER = True` and `SECURE_CONTENT_TYPE_NOSNIFF = True` are enabled.

---

## 6. Audit Logging & Forensic Incident Response
Every sensitive administrative event is logged to `accounts_auditlog`:
- `ORG_ACTIVATED` / `ORG_SUSPENDED`
- `ORG_APPROVED` / `ORG_REJECTED`
- `USER_ROLE_CHANGED` / `USER_STATUS_TOGGLED`
- `JOB_CREATED` / `JOB_DELETED` / `JOB_ARCHIVED`
- `APPLICATION_STATUS_UPDATED` / `INTERVIEW_SCHEDULED`
- `UNAUTHORIZED_OWNER_AREA_ACCESS_ATTEMPT`

Platform Owners can export the complete audit trail as a signed CSV report directly from `/owner/export-report/`.
