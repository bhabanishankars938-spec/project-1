# HireNexa Enterprise Role-Based Access Control (RBAC) & Permission Matrix

## Comprehensive Multi-Tenant Authorization Specification & Role Hierarchy

---

## 1. System Role Hierarchy

HireNexa enforces a strict multi-tenant Role-Based Access Control model across five distinct user personas:

```
                  ┌────────────────────────┐
                  │ 1. Platform Owner      │ (Superuser / Master Admin)
                  └───────────┬────────────┘
                              │
                  ┌───────────▼────────────┐
                  │ 2. Organization Admin  │ (Company Tenant Owner)
                  └───────────┬────────────┘
                              │
                  ┌───────────▼────────────┐
                  │ 3. HR Recruiter        │ (Hiring Manager / Team Recruiter)
                  └────────────────────────┘

┌────────────────────────────┐          ┌────────────────────────────┐
│ 4. Candidate / Student     │          │ 5. Freelance Professional  │
└────────────────────────────┘          └────────────────────────────┘
```

---

## 2. Dedicated Vanity Login Gateways

To provide seamless, persona-specific onboarding while eliminating authorization ambiguity, HireNexa implements dedicated vanity gateways:

| Persona | Gateway Route | Target Dashboard | Permitted Roles |
|---|---|---|---|
| **Candidate / Job Seeker** | `/candidate/login/` | `/dashboard/` | `ROLE_CANDIDATE` |
| **HR Recruiter** | `/hr/login/` | `/recruiter/dashboard/` | `ROLE_RECRUITER`, `ROLE_COMPANY_ADMIN` |
| **Company Administrator** | `/company/login/` | `/company/admin/` | `ROLE_COMPANY_ADMIN` |
| **Platform Owner** | `/owner/login/` | `/admin/` (or `/owner/dashboard/`) | Superusers (`is_superuser=True`) |
| **Unified Portal** | `/login/` | Smart Redirect based on Role | All Active Roles |

---

## 3. Comprehensive Domain Permission Matrix

Legend:
- **`CRUD`**: Full Create, Read, Update, Delete authority
- **`CRU`**: Create, Read, Update
- **`R`**: Read-only
- **`R-Self`**: Read-only for own data/profile
- **`U-Self`**: Update only own data/profile
- **`X`**: Access Denied (HTTP 403 Forbidden)

| Functional Domain / Capability | Platform Owner | Organization Admin | HR Recruiter | Candidate / Fresher | Freelancer |
|---|---|---|---|---|---|
| **User & Tenant Management** |
| Create / Deactivate Organizations | CRUD | X | X | X | X |
| Manage Recruiter Team Members | CRUD | CRUD | X | X | X |
| View Organization Audit Logs | CRUD | R (Own Tenant) | X | X | X |
| Delete Own Account (GDPR) | CRUD | U-Self | U-Self | U-Self | U-Self |
| **Recruitment & Job Pipeline** |
| Post & Publish Jobs | CRUD | CRUD (Own) | CRUD (Assigned) | X | X |
| View Job Applications | CRUD | CRUD (Own) | CRUD (Assigned) | R-Self | X |
| Update Candidate Application Stage | CRUD | CRUD (Own) | CRUD (Assigned) | X | X |
| Schedule Video Interviews | CRUD | CRUD (Own) | CRUD (Assigned) | X | X |
| Join Video Interview Room | CRUD | R (Tenant) | CRUD (Host) | R (Invitee) | X |
| Submit Interview Scorecards | CRUD | CRUD (Own) | CRUD (Assigned) | X | X |
| Verify Corporate Office Addresses | CRUD | CRUD (Own) | R (Own) | R (Public) | R (Public) |
| **CBT Examination Engine** |
| Create Official PYQ / Curated Exams| CRUD | X | X | X | X |
| Verify & Publish Question Bank | CRUD | X | X | X | X |
| Launch Topic Test (16Q/21Min) | CRUD | X | X | CRUD (Up to 5) | X |
| View Exam Result & Derivations | CRUD | X | X | R-Self | X |
| Attempt Lockout Override | CRUD | X | X | X | X |
| **AI Career Optimization (ACO)** |
| Run ACO 8-Module Analysis | CRUD | X | X | CRUD (Self) | CRUD (Self) |
| Access Skill Gap & 4-Week Plan | CRUD | X | X | R-Self | R-Self |
| ATS Resume Optimization | CRUD | X | X | CRUD (Self) | CRUD (Self) |
| **Freelance Gig Marketplace** |
| Post Freelance Gig Requirement | CRUD | CRUD | CRUD | X | X |
| Submit Gig Proposal / Bid | CRUD | X | X | X | CRUD |
| Deliver Gig Milestones | CRUD | X | X | X | CRUD |

---

## 4. Multi-Tenant Data Isolation Rules

1. **Tenant Filtering at ORM Level**:
   - In `recruitment/views.py`, recruiter queries are strictly scoped:
   ```python
   Job.objects.filter(organization=request.user.organization)
   Application.objects.filter(job__organization=request.user.organization)
   Interview.objects.filter(job__organization=request.user.organization)
   ```
2. **Horizontal Privilege Escalation Prevention**:
   - Passing an unauthorized `pk` in `/interviews/<pk>/room/` or `/applications/<pk>/` validates tenant ownership before rendering or returns an immediate `Http404` or `PermissionDenied`.
3. **Session Verification**:
   - `request.user.is_authenticated` accompanied by role-checking decorators (`@recruiter_required`, `@candidate_required`, `@organization_admin_required`).
