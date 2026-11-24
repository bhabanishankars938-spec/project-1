# HireNexa V3 Enterprise SaaS – API & Endpoint Documentation

## 1. Gateway & Authentication Endpoints

### 1.1 Vanity Login Gateways
- **GET `/owner/login/`**: Platform Owner master administrative sign-in portal.
- **GET `/company/login/`**: Company Administrator corporate portal sign-in.
- **GET `/hr/login/`**: HR Recruiter & talent acquisition sign-in.
- **GET `/candidate/login/`**: Student & candidate career portal sign-in.
- **GET `/freelancer/login/`**: Independent contractor & freelance gig portal sign-in.
- **GET `/roles/`**: Unified role selection directory.

### 1.2 Authentication Actions
- **POST `/accounts/login/`**: Authenticates user credentials via Argon2id. Sets secure HTTP-only session cookie.
- **POST `/accounts/logout/`**: Terminates active session and invalidates session token.
- **POST `/accounts/signup/`**: Registers candidate or company administrator account.
- **GET `/dashboard/`**: Central intelligent router redirecting authenticated users to their authorized workspace.

---

## 2. Platform Owner Master Control API (`/owner/`)
*Authorization*: Strict Platform Owner (`role='OWNER'` or `is_superuser=True`).

### 2.1 Owner Dashboard
- **GET `/owner/`** (or `/owner/dashboard/`): Returns system health, 12 core KPIs (MRR, active/pending/suspended companies, candidate counts, vacancy targets), pending approvals, dynamic SaaS tiers, and recent payments.

### 2.2 Company Tenant Governance
- **POST `/owner/orgs/<pk>/approve/`**: Approves pending corporate registration. Sets `verification_status='APPROVED'` and `is_active=True`.
- **POST `/owner/orgs/<pk>/reject/`**: Rejects company registration.
  - *Payload*: `rejection_reason` (string, required).
  - *Action*: Sets `verification_status='REJECTED'`, `is_active=False`, records reason in audit trail.
- **POST `/owner/orgs/<pk>/toggle/`**: Toggles company operational status between Active and Suspended.
- **GET `/owner/orgs/<pk>/detail/`**: Deep administrative view of company profile, provisioned HR recruiters, posted vacancies, applicant stats, and payment history.

### 2.3 SaaS Subscription Plans & Monetization
- **GET `/owner/plans/`**: Lists all dynamic subscription tiers.
- **GET / POST `/owner/plans/create/`**: Creates a new pricing tier.
  - *Payload*: `name`, `slug`, `tier`, `price_monthly`, `annual_price`, `currency`, `max_active_jobs`, `max_hr_seats`, `max_resumes_per_month`, `ai_matching_enabled`.
- **GET / POST `/owner/plans/<pk>/edit/`**: Updates subscription tier configuration.
- **POST `/owner/plans/<pk>/delete/`**: Soft-deactivates or deletes unused pricing tiers.

### 2.4 User Governance & Audit Reports
- **POST `/owner/users/<pk>/toggle/`**: Activates or suspends any user account.
- **POST `/owner/users/<pk>/role/`**: Updates user authorization role (`OWNER`, `COMPANY_ADMIN`, `RECRUITER`, `CANDIDATE`, `FREELANCER`).
- **GET `/owner/export-report/`**: Generates a signed CSV export of platform audit logs.

---

## 3. Company Admin & HR Recruiter API

### 3.1 Company Management
- **GET `/company/`**: Corporate workspace overview with team members, active jobs, round funnels, and subscription limits.
- **GET / POST `/company/add-hr/`**: Provisions a new HR recruiter account within the organization.
- **GET / POST `/company/profile/edit/`**: Updates corporate legal details, industry, size, and branding.

### 3.2 6-Step Vacancy Wizard API
- **GET / POST `/jobs/create/`**: Opens the 6-step recruitment wizard.
  - *Step 1*: `title`, `department`, `target_course`, `job_type`, `workplace_type`, `location`, `description`.
  - *Step 2*: `salary_currency`, `salary_period`, `salary_min`, `salary_max`, `is_salary_negotiable`, `display_salary_publicly`.
  - *Step 3*: `vacancies`, `hiring_rounds`.
  - *Step 4*: `experience_level`, `min_experience_years`, `required_skills`.
  - *Step 5*: `screening_questions`, `is_ai_screening_enabled`, `is_active`, `status`.
  - *Step 6*: Pre-publication review.
- **GET / POST `/jobs/<pk>/edit/`**: Updates vacancy configuration via the 6-step wizard.
- **POST `/jobs/<pk>/duplicate/`**: Clones an existing vacancy into an active copy (`Copy of ...`).
- **POST `/jobs/<pk>/delete/`**: Deletes vacancy or soft-archives (`action='archive'`).
- **POST `/jobs/<pk>/headcount/`**: Adjusts hiring quota (`delta=+1` or `-1`).
- **POST `/jobs/<pk>/toggle-status/`**: Toggles between `ACTIVE` and `PAUSED`.

### 3.3 Candidate Evaluation & Interview Funnel
- **GET `/jobs/<pk>/applicants/`**: Candidate pipeline table with round funnels (`APPLIED`, `ROUND_1`, `ROUND_2`, `ROUND_3`, `FINAL_ROUND`, `HIRED`).
- **POST `/applications/<pk>/status/`**: Transitions candidate through hiring stages.
  - *Payload*: `status` (`ROUND_1`, `ROUND_2`, `HIRED`, `REJECTED`, etc.), `recruiter_notes`, `rating`, `rejection_reason`.
- **GET / POST `/applications/<pk>/interview/`**: Schedules an interview assessment.
  - *Payload*: `round_name`, `scheduled_at`, `mode`, `meeting_link`, `location`, `notes`.

---

## 4. Candidate & Freelancer API

### 4.1 Candidate Workflow
- **GET `/candidate/`**: Candidate dashboard with application trackers, interview invitations, and profile completion bar.
- **POST `/resumes/upload/`**: Uploads and triggers 7-Agent parsing on PDF/DOCX resumes.
- **GET `/resumes/<pk>/download/`**: Securely serves authenticated candidate resume.
- **POST `/candidate/education/add/`**: Appends degree, university, GPA.
- **POST `/candidate/skill/add/`**: Appends technical skill and proficiency.
- **POST `/candidate/project/add/`**: Appends project title, repo link, technologies.
- **POST `/jobs/<pk>/apply/`**: Submits application with selected resume and screening question responses.

### 4.2 Freelancer Workflow
- **GET `/freelancer/`**: Freelancer project workspace and proposal tracker.
- **GET `/projects/`**: Lists active freelance projects with skill filters.
- **GET / POST `/projects/<pk>/apply/`**: Submits bid amount, estimated days, and cover letter.
- **GET / POST `/projects/create/`**: Clients post new freelance project requirements.

---

## 5. Official News & Announcements Broadcast Engine
- **GET `/news/`**: Public and authenticated notice hub with category and audience filters.
- **GET / POST `/news/create/`**: Publishes new announcement.
  - *Scope*: Platform-wide for Owner; company-scoped for Company Admin.
  - *Payload*: `title`, `category`, `target_audience`, `priority`, `summary`, `content`, `attachment`, `is_pinned`, `expires_at`.
- **GET `/news/<slug>/`**: Detailed notice view with attached circulars.
- **GET / POST `/news/<pk>/edit/`**: Updates circular content and priority.
- **POST `/news/<pk>/delete/`**: Permanently removes announcement.

---

## 6. Startup Platform Modules & Endpoints

### 6.1 Verified Companies Directory & Career Hub
- **GET `/companies/`**: Public directory of verified hiring companies with industry filters and active vacancies count.
- **GET / POST `/resume-analyzer/`**: Public and candidate AI diagnostic engine. Uploads PDF/DOCX, extracts competencies, and benchmarks against target roles with explainable scores.
- **GET `/resources/`**: Career development hub with interview cheat-sheets and placement guides.
- **GET `/terms/`**: Platform Terms of Service.
- **GET `/privacy/`**: Privacy Policy and Data Processing disclosures.

### 6.2 Candidate Actions & Job Bookmarks
- **POST `/jobs/<pk>/save/`**: Toggles bookmarking for an active job (supports AJAX JSON response).
- **GET `/jobs/saved/`**: Lists all saved/bookmarked jobs for the authenticated candidate.
- **GET `/jobs/recommended/`**: Personalized AI job recommendations ranked by skill overlap and academic stream.
- **POST `/applications/<pk>/withdraw/`**: Candidate voluntarily withdraws an ongoing application.
- **GET `/resumes/<pk>/preview/`**: Inline browser preview of verified resume document.
- **POST `/resumes/<pk>/delete/`**: Permanently removes resume from candidate profile.

### 6.3 Moderation & Compliance
- **POST `/report/`**: Authenticated users file a `UserReport` flagging suspicious jobs or projects.
- **POST `/owner/reports/<pk>/resolve/`**: Platform Owner resolves or dismisses flagged moderation reports.
- **GET / POST `/company/verification-upload/`**: Company Admins submit business incorporation documents (Certificate of Incorporation, GSTIN, PAN).
- **POST `/owner/docs/<pk>/review/`**: Platform Owner audits, approves, or rejects submitted company verification credentials.

### 6.4 Notifications & Interview Lifecycle
- **GET `/notifications/`**: Activity center displaying application status advancements and interview invites.
- **POST `/notifications/mark-read/`**: Marks all unread user notifications as read.
- **POST `/interviews/<pk>/schedule/`**: Recruiter schedules an interview specifying date/time, duration, and provider (`INTERNAL`, `ZOOM`, `GOOGLE_MEET`, `IN_PERSON`, `PHONE`). Automatically provisions Zoom meetings or internal room tokens.
- **GET / POST `/interviews/<pk>/reschedule/`**: Recruiter reschedules an interview with date/time adjustments.
- **POST `/interviews/<pk>/cancel/`**: Recruiter cancels an interview with automated applicant alert.
- **GET `/interviews/<pk>/room/`**: Dedicated Virtual Interview Studio with embedded WebRTC / video controls, candidate profile summary, and recruiter scoring form.

### 6.5 GeoHire Location Intelligence API
- **GET `/api/v1/locations/autocomplete/`**: Sub-15ms prefix query endpoint returning matching Indian cities, districts, states, and PIN code clusters.
- **GET `/companies/<slug>/trust/`**: Public corporate verification profile with dual physical addresses (Registered Corporate Headquarters vs Operating Branch Office), Google Maps link, and turn-by-turn directions link.

