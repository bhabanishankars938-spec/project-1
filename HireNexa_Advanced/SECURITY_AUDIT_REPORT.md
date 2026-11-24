# HireNexa Enterprise Cybersecurity & Security Audit Report

## Security Architecture, Cryptographic Standards, Authentication Defense & Vulnerability Assessment

---

## 1. Executive Security Assessment

HireNexa Enterprise 2.0 has been hardened against the **OWASP Top 10 Web Application Vulnerabilities** and enterprise data security requirements.

| Threat Category | Risk Assessment | Mitigating Security Control | Verification Status |
|---|---|---|---|
| **A01: Broken Access Control** | High | Multi-tenant ORM scoping, role decorators, IDOR prevention | **VERIFIED HARDENED** |
| **A02: Cryptographic Failures** | High | Argon2id password hashing, TLS 1.3, encrypted session tokens | **VERIFIED HARDENED** |
| **A03: Injection (SQL / Command)** | High | 100% parameterized queries via Django ORM, input sanitization | **VERIFIED HARDENED** |
| **A04: Insecure Design** | Medium | Server-authoritative scoring & attempt lockout enforcement | **VERIFIED HARDENED** |
| **A05: Security Misconfiguration** | Medium | Environment-isolated secrets, debug disabled in staging | **VERIFIED HARDENED** |
| **A06: Vulnerable Components** | Low | Python 3.13.3, Django 6.1.3 latest stable dependencies | **VERIFIED HARDENED** |
| **A07: Identification & Auth Failures** | High | 6-digit OTP rate limiting, multi-portal vanity routing | **VERIFIED HARDENED** |
| **A08: Software & Data Integrity** | Medium | Immutable exam attempt snapshots, HMAC interview tokens | **VERIFIED HARDENED** |
| **A09: Security Logging & Monitoring** | Low | Audit logging for role transitions, logins, and exam submissions | **VERIFIED HARDENED** |
| **A10: Server-Side Request Forgery** | Low | Whitelisted API proxying, sandboxed background workers | **VERIFIED HARDENED** |

---

## 2. Authentication & Identity Hardening

### A. Argon2id Password Hashing
Password storage utilizes the modern **Argon2id** key derivation function (via `django[argon2]`):
- Memory cost: 65,536 KiB
- Time cost: 3 iterations
- Parallelism: 4 threads
- Protection against GPU and ASIC brute-force password cracking.

### B. Two-Factor Authentication (OTP)
- **Entropy**: Cryptographically secure 6-digit numerical codes generated via `secrets.randbelow()`.
- **Expiration Window**: Strict 15-minute validity (`datetime.timedelta(minutes=15)`).
- **Single-Use Invalidation**: OTP is immediately marked `is_used=True` upon verification.
- **Rate Limiting**: Maximum 3 OTP requests per 10 minutes per IP/User to prevent SMS/email flooding.

---

## 3. Session & Transport Layer Security

In `config/settings.py`:
- `SESSION_COOKIE_HTTPONLY = True`: Blocks JavaScript access to session identifiers, preventing XSS-based session theft.
- `SESSION_COOKIE_SECURE = True` (Production): Restricts cookies to HTTPS-only transmissions.
- `CSRF_COOKIE_HTTPONLY = True`: Hardens CSRF tokens against client-side tampering.
- `SESSION_COOKIE_SAMESITE = 'Lax'`: Mitigates Cross-Site Request Forgery across third-party contexts.
- `X_FRAME_OPTIONS = 'DENY'`: Mitigates UI clickjacking attacks.
- `SECURE_CONTENT_TYPE_NOSNIFF = True`: Prevents MIME-type confusion attacks.

---

## 4. Multi-Tenant Isolation & IDOR Defense

In multi-tenant SaaS platforms, Insecure Direct Object References (IDOR) are the primary vector for data leakage.

### Protective Architecture
1. **Tenant Isolation by Construction**:
   Recruiters cannot query jobs or candidates outside their assigned `Organization`:
   ```python
   def get_queryset(self):
       return Job.objects.filter(organization=self.request.user.organization)
   ```
2. **Interview Room Token Validation**:
   In `/interviews/<pk>/room/`, authorization verifies:
   - Recruiter belongs to the scheduling organization, OR
   - Candidate matches `interview.application.candidate`.
   - Unauthorized attempts return an immediate HTTP 403 Forbidden.

---

## 5. Examination Anti-Cheating & Integrity Guardrails

1. **Client Disconnection Resilience**: Exam timer computes against backend `started_at` timestamp. Client-side clock tampering cannot extend the 21-minute limit.
2. **Server-Side Decimal Scoring**: Client submits only option IDs (`A`, `B`, `C`, `D`). The calculation of $+1.00$ or $-0.25$ occurs exclusively in `assessments/services.py`.
3. **Attempt Limit Enforcement**: The 5-attempt ceiling is verified by querying historical attempts in an atomic database transaction before instantiating a new session.
