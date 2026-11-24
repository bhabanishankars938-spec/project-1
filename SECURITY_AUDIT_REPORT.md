# SECURITY AUDIT & RBAC PERMISSION REPORT
## HireNexa Cybersecurity & Platform Governance Team

---

### Security Architecture Highlights

#### 1. Authentication & Multi-Factor Security
- **Argon2 / PBKDF2 Password Hashing**: Passwords stored using cryptographic salts and high-iteration PBKDF2.
- **Rate-Limiting & Brute-Force Lockout**: 5 failed login attempts trigger an exponential backoff lockout.
- **Two-Factor Authentication**: Email and Console SMS OTP verification with 15-minute token expiry.
- **Session Protection**: `SESSION_COOKIE_HTTPONLY = True`, `CSRF_COOKIE_HTTPONLY = False` (for AJAX compatibility), `SECURE_BROWSER_XSS_FILTER = True`.

#### 2. Role-Based Access Control (RBAC)
- Multi-role isolation enforced at both view and API levels:
  - `User.Role.CANDIDATE`: Restricted to candidate portfolios, job applications, exam assessments.
  - `User.Role.RECRUITER` / `COMPANY_ADMIN`: Restricted to organization job postings, applicant management, and candidate shortlists.
  - `User.Role.OWNER`: Full administrative governance, company verification, financial audit logs.

#### 3. SQL Injection & Cross-Site Scripting (XSS) Prevention
- Zero raw SQL queries; all database interactions utilize Django ORM parameterized queries.
- Template rendering enforces automatic HTML escaping on all dynamic fields (`{{ job.title }}`, `{{ job.company_name }}`).
- Rich text fields sanitized with `striptags` before rendering excerpts.
