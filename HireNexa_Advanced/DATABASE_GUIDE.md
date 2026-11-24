# HireNexa V3 Enterprise SaaS – Database Guide

## 1. Overview & Database Architecture
HireNexa operates on a resilient dual-database design:
- **Primary Relational Store**: PostgreSQL 16 (or local SQLite in development mode).
- **ORM & Migrations**: Django ORM with strict referential integrity, foreign key cascades, and transactional state updates.
- **Audit Logging Subsystem**: Real-time structured immutable audit events (`accounts_auditlog`).

---

## 2. Entity Relationship Model & Table Definitions

```
 ┌──────────────────────┐        1:N        ┌────────────────────────────┐
 │ accounts_user        ├──────────────────►│ recruitment_organization-  │
 │ (Owner, HR, Cand, FL)│                   │ member                     │
 └──────────┬───────────┘                   └─────────────┬──────────────┘
            │                                             │ N:1
            │ 1:1                                         ▼
 ┌──────────┴───────────┐                   ┌────────────────────────────┐
 │ recruitment_candidate│                   │ recruitment_organization   │
 │ profile              │                   │ (Company Tenant)           │
 └──────────────────────┘                   └─────────────┬──────────────┘
            │                                             │ 1:N
            │ 1:N                                         ▼
 ┌──────────┴───────────┐        N:1        ┌────────────────────────────┐
 │ recruitment_resume   │◄──────────────────┤ recruitment_job            │
 └──────────┬───────────┘                   │ (Requisitions)             │
            │                               └─────────────┬──────────────┘
            │ 1:N                                         │ 1:N
            ▼                                             ▼
 ┌──────────────────────┐                   ┌────────────────────────────┐
 │ recruitment_aimatch- │                   │ recruitment_application    │
 │ result               │                   │ (Pipeline candidate state) │
 └──────────────────────┘                   └─────────────┬──────────────┘
                                                          │ 1:N
                                                          ▼
                                            ┌────────────────────────────┐
                                            │ recruitment_interview      │
                                            └────────────────────────────┘
```

### Table 1: `accounts_user`
- `id` (BIGINT, PRIMARY KEY): Unique identifier.
- `username` (VARCHAR 150, UNIQUE): User handle.
- `email` (VARCHAR 254, UNIQUE): Official contact email.
- `password` (VARCHAR 128): Argon2id salted and hashed digest.
- `role` (VARCHAR 20): One of `OWNER`, `COMPANY_ADMIN`, `RECRUITER`, `CANDIDATE`, `FREELANCER`.
- `phone_number` (VARCHAR 20, BLANK): International dial format.
- `is_verified` (BOOLEAN): Email/identity verification state.
- `is_active` (BOOLEAN): Soft activation flag.
- `is_staff` / `is_superuser` (BOOLEAN): Platform administration privileges.

### Table 2: `recruitment_organization`
- `id` (BIGINT, PRIMARY KEY).
- `name` (VARCHAR 160, UNIQUE): Corporate entity name.
- `slug` (SLUG 80, UNIQUE): URL vanity handle.
- `industry` (VARCHAR 120): Business sector.
- `company_size` (VARCHAR 50): Number of employees.
- `verification_status` (VARCHAR 20): `PENDING`, `APPROVED`, `REJECTED`.
- `rejection_reason` (TEXT): Audit documentation deficiency feedback.
- `is_active` (BOOLEAN): Owner activation/suspension toggle.

### Table 3: `recruitment_organizationmember`
- `id` (BIGINT, PRIMARY KEY).
- `organization_id` (FK -> `recruitment_organization`, CASCADE).
- `user_id` (FK -> `accounts_user`, CASCADE).
- `role` (VARCHAR 30): `ADMIN`, `HR`, `INTERVIEWER`.
- `can_post_jobs` / `can_schedule_interviews` / `can_download_resumes` (BOOLEAN).
- `is_active` (BOOLEAN).

### Table 4: `recruitment_job`
- `id` (BIGINT, PRIMARY KEY).
- `organization_id` (FK -> `recruitment_organization`, CASCADE).
- `recruiter_id` (FK -> `accounts_user`, CASCADE).
- `title` (VARCHAR 160): Position name.
- `target_course` (VARCHAR 40): Academic discipline filter (`MCA`, `MBA`, `BTECH`, `ALL`).
- `vacancies` (POSITIVE INT): Headcount target quota.
- `hiring_rounds` (VARCHAR 300): Round progression sequence.
- `job_type` / `experience_level` / `workplace_type` (VARCHAR 40).
- `salary_currency` (VARCHAR 10): `INR`, `USD`, `EUR`, `GBP`.
- `salary_period` (VARCHAR 20): `MONTHLY`, `ANNUAL`.
- `salary_min` / `salary_max` (DECIMAL 12, 2).
- `is_salary_negotiable` / `display_salary_publicly` (BOOLEAN).
- `required_skills` (VARCHAR 700): Comma-separated canonical skills.
- `screening_questions` (JSONB): Pre-screening questions array.
- `is_ai_screening_enabled` (BOOLEAN).
- `status` (VARCHAR 20): `ACTIVE`, `PAUSED`, `FILLED`, `CLOSED`.
- `is_featured` (BOOLEAN): Promoted by Platform Owner.

### Table 5: `recruitment_application`
- `id` (BIGINT, PRIMARY KEY).
- `job_id` (FK -> `recruitment_job`, CASCADE).
- `candidate_id` (FK -> `accounts_user`, CASCADE).
- `resume_id` (FK -> `recruitment_resume`, CASCADE).
- `status` (VARCHAR 30): `APPLIED`, `SCREENING`, `ROUND_1`, `ROUND_2`, `ROUND_3`, `FINAL_ROUND`, `OFFERED`, `HIRED`, `REJECTED`, `WITHDRAWN`.
- `recruiter_notes` (TEXT).
- `recruiter_rating` (INT): 1 to 5 stars.
- `rejection_reason` (TEXT).

### Table 6: `recruitment_subscriptionplan`
- `id` (BIGINT, PRIMARY KEY).
- `name` (VARCHAR 60, UNIQUE).
- `slug` (SLUG 80, UNIQUE).
- `tier` (VARCHAR 30): `FREE`, `GROWTH`, `PRO`, `ENTERPRISE`.
- `price_monthly` / `annual_price` (DECIMAL 10, 2).
- `currency` (VARCHAR 10).
- `max_active_jobs` / `max_hr_seats` / `max_resumes_per_month` (INT).
- `ai_matching_enabled` / `advanced_analytics` / `priority_support` (BOOLEAN).

### Table 7: `recruitment_payment`
- `id` (BIGINT, PRIMARY KEY).
- `organization_id` (FK -> `recruitment_organization`, CASCADE).
- `plan_id` (FK -> `recruitment_subscriptionplan`, SET_NULL).
- `amount` (DECIMAL 10, 2).
- `currency` (VARCHAR 10).
- `transaction_id` (VARCHAR 120, UNIQUE).
- `provider` (VARCHAR 40): `RAZORPAY`, `STRIPE`.
- `status` (VARCHAR 20): `SUCCESS`, `PENDING`, `FAILED`.
- `verified_at` (DATETIME).

### Table 8: `accounts_auditlog`
- `id` (BIGINT, PRIMARY KEY).
- `user_id` (FK -> `accounts_user`, SET_NULL).
- `action` (VARCHAR 60): Event tag.
- `resource_type` (VARCHAR 60).
- `resource_id` (VARCHAR 120).
- `ip_address` (VARCHAR 45).
- `details` (JSONB): Structured contextual data.
- `timestamp` (DATETIME): Immutable timestamp.

---

## 3. Multi-Tenant Data Isolation Strategy
1. **Tenant Association**: Every corporate asset (`Job`, `Application`, `Interview`, `Payment`) carries a non-null `organization_id` foreign key.
2. **Backend Enforcement**: Views filter strictly by `organization = get_user_org(request.user)`.
3. **Owner Super-Tenancy**: Platform Owners (`User.Role.OWNER` or `is_superuser=True`) have platform-wide read/write permissions for moderation.

---

## 4. Database Maintenance & Backup Runbook

### Automatic Nightly Backup Script (`/opt/hirenexa/backup_db.sh`)
```bash
#!/bin/bash
BACKUP_DIR="/opt/hirenexa/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
mkdir -p "$BACKUP_DIR"

pg_dump -U hirenexa_prod_user -h 127.0.0.1 hirenexa_enterprise_db | gzip > "$BACKUP_DIR/hirenexa_db_$TIMESTAMP.sql.gz"
find "$BACKUP_DIR" -type f -name "*.sql.gz" -mtime +14 -exec rm {} \;
```

### Restore Database Runbook
```bash
gunzip -c /opt/hirenexa/backups/hirenexa_db_20261115.sql.gz | psql -U hirenexa_prod_user -h 127.0.0.1 -d hirenexa_enterprise_db
```
