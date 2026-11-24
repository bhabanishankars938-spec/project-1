# HireNexa V3 Enterprise SaaS – Project Architecture & System Design

## 1. Executive Architecture Summary
HireNexa is an enterprise-grade AI-powered multi-tenant recruitment and talent intelligence SaaS platform. The system facilitates end-to-end talent acquisition for corporations, academic placement cells, candidates, and freelance talent pools.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        HIRENEXA PLATFORM ARCHITECTURE                  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        PRESENTATION & PORTALS                          │
│  /owner/login     /company/login     /hr/login     /candidate/login    │
│  Owner Dashboard  Company Admin      HR Workspace  Candidate Portal    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   AUTHENTICATION & SECURITY LAYER                      │
│  Argon2id Hashing  ·  5-Tier RBAC  ·  Multi-Tenant Boundary Guards    │
│  Audit Trail Logging  ·  Double Submit CSRF  ·  Magic Byte Validation │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       MODULAR 7-AGENT AI ENGINE                        │
│  1. Data Quality Agent         │  5. Semantic Matching Agent           │
│  2. Resume Parsing Agent       │  6. Candidate Explanation Agent       │
│  3. Job Understanding Agent    │  7. Recruitment Assistant Agent       │
│  4. Skill Matching Agent       │                                       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       BUSINESS LOGIC SERVICES                          │
│  6-Step Job Wizard  ·  Round Pipeline Funnel  ·  Interview Scheduler   │
│  Official News Broadcast Engine  ·  Verified MRR / Payment Gateway    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        PERSISTENCE & STORAGE                           │
│  PostgreSQL 16 Multi-Tenant RDBMS  ·  Private Protected Object Storage │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. The Four Distinct Portals & Unified Domain
HireNexa delivers dedicated portals under a unified domain with role-tailored workspaces:
1. **Platform Owner Control Center (`/owner/`)**:
   - Master KPI telemetry: MRR, active/pending/suspended companies, hiring targets.
   - Company verification queue: One-click approval and documented rejection reasons.
   - Dynamic SaaS pricing tier governance and real-time revenue audits.
   - Author moderation: Add/delete/feature platform vacancies and broadcast official notices.
2. **Company Admin Workspace (`/company/`)**:
   - Corporate identity, profile branding, and workplace configurations.
   - Recruiter seat provisioning and team management.
   - Subscription limits, active jobs count, and candidate pipeline aggregates.
3. **HR Recruiter Workspace (`/hr/`)**:
   - Advanced 6-Step Job Creation Studio with dynamic compensation modeling.
   - Candidate pipeline management across evaluation rounds (`ROUND_1` to `FINAL_ROUND`).
   - AI match scoring, radar diagnostics, and interview scheduling.
4. **Candidate Career Portal (`/candidate/`)**:
   - Resume upload with automated field extraction.
   - Skill, education, and project enrichment cards.
   - Live interview schedule reminders and real-time stage progress trackers.
5. **Freelancer Workspace (`/freelancer/`)**:
   - Project directory, proposal submissions, hourly rate configuration, and portfolio showcase.

---

## 3. Modular 7-Agent AI Recruitment Architecture
The AI engine in `recruitment/services.py` coordinates 7 distinct specialized agents:

```
[ Uploaded Resume (PDF/DOCX) ]
             │
             ▼
   ┌───────────────────┐
   │ 1. Data Quality   │──► Magic Byte Verification & Integrity Scoring
   │    Agent          │
   └─────────┬─────────┘
             │
             ▼
   ┌───────────────────┐
   │ 2. Resume Parsing │──► Structured extraction (Skills, Education, Years)
   │    Agent          │
   └─────────┬─────────┘
             │
             ▼
   ┌───────────────────┐     ┌───────────────────┐
   │ 4. Skill Matching │◄────┤ 3. Job Understand-│◄── [ Job Requisition ]
   │    Agent          │     │    ing Agent      │
   └─────────┬─────────┘     └───────────────────┘
             │
             ▼
   ┌───────────────────┐
   │ 5. Semantic Match-│──► Sentence-Transformer contextual similarity
   │    ing Agent      │
   └─────────┬─────────┘
             │
             ▼
   ┌───────────────────┐
   │ 6. Candidate      │──► Transparent rationale, strengths, gap diagnosis
   │    Explanation    │
   └─────────┬─────────┘
             │
             ▼
   ┌───────────────────┐
   │ 7. Recruitment    │──► Custom technical questions for HR interviewers
   │    Assistant      │
   └───────────────────┘
```

1. **`DataQualityAgent`**: Inspects binary magic numbers, file size bounds, SHA-256 hashes, and text corruption/OCR degradation.
2. **`ResumeParsingAgent`**: Normalizes and extracts contact emails, phones, university degrees, GPA, and work experience years.
3. **`JobUnderstandingAgent`**: Deconstructs job requisitions into mandatory skills, nice-to-have skills, target academic degree (MCA, MBA, BTech), and seniority levels.
4. **`SkillMatchingAgent`**: Cross-references candidate skills against a 130+ technical and business taxonomy using exact and synonym expansions.
5. **`SemanticMatchingAgent`**: Computes contextual vector cosine similarity using `all-MiniLM-L6-v2` embeddings (with resilient lexical TF-IDF fallback).
6. **`CandidateExplanationAgent`**: Produces explainable AI rationale: fit tier, key strengths, missing competencies, and candidate recommendations.
7. **`RecruitmentAssistantAgent`**: Generates tailored interview questionnaires targeting candidate gaps for hiring panels.

---

## 4. Multi-Tenant Isolation & Zero-Leakage Architecture
- **Tenant Data Isolation**: Every organizational entity belongs to an `Organization`. Backend views enforce `organization = get_user_org(request.user)` on all querysets.
- **Cross-Tenant Guardrails**: Direct attempts to inspect or mutate another company's vacancy, applicant, or interview records trigger `PermissionDenied` (HTTP 403).
- **Public Visibility vs Private Data**: Candidate resumes are never stored in public directories; they are served via authenticated, permission-checked streaming endpoints.

---

## 5. End-to-End Data Lifecycle

```
[ Company Registration ]
           │
           ▼
[ Owner Verification Queue ] ──► Reject (With Reason) / Approve
           │ (Approved)
           ▼
[ Company Provisioning ] ──► Admin invites HR Recruiters
           │
           ▼
[ 6-Step Job Studio ] ──► Salary Brackets, Rounds & Pre-Screening Questions
           │
           ▼
[ Candidate Ingestion ] ──► Resume Upload & 7-Agent AI Scoring
           │
           ▼
[ Multi-Round Funnel ] ──► Round 1 ──► Round 2 ──► Final ──► Hired
           │
           ▼
[ Analytics Telemetry ] ──► Real-time DB aggregates, Quota decrement & MRR
```
