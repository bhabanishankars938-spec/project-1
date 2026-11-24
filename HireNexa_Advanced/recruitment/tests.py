import io
from pathlib import Path
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse

from accounts.models import User, AuditLog
from recruitment.models import (
    Organization, OrganizationMember, RecruiterProfile, CandidateProfile,
    Job, Resume, Application, AIMatchResult, Interview, Notification, ShortlistedCandidate,
    NewsAnnouncement, SubscriptionPlan, Payment
)
from recruitment.services import (
    extract_skills, extract_education, extract_experience_years,
    calculate_match, validate_resume_file,
    DataQualityAgent, ResumeParsingAgent, JobUnderstandingAgent,
    SkillMatchingAgent, SemanticMatchingAgent, CandidateExplanationAgent,
    RecruitmentAssistantAgent
)


class MatchingAndExtractionServiceTests(TestCase):
    def test_extract_skills_extended_taxonomy(self):
        text = "Experienced Senior Engineer skilled in Python, Django REST Framework, FastAPI, PostgreSQL, Docker, Kubernetes, React, TypeScript, and AWS cloud."
        skills = extract_skills(text)
        self.assertIn("python", skills)
        self.assertIn("django", skills)
        self.assertIn("fastapi", skills)
        self.assertIn("postgresql", skills)
        self.assertIn("docker", skills)
        self.assertIn("kubernetes", skills)
        self.assertIn("react", skills)
        self.assertIn("typescript", skills)
        self.assertIn("aws", skills)

    def test_explainable_skill_match_and_recommendations(self):
        resume_text = "I am a Python and Django developer with PostgreSQL database knowledge."
        required = ["python", "django", "docker", "kubernetes"]
        result = calculate_match(resume_text, required, "Backend developer opening")
        self.assertEqual(result["skill_score"], 50.0)
        self.assertIn("python", result["matched"])
        self.assertIn("django", result["matched"])
        self.assertIn("docker", result["missing"])
        self.assertIn("kubernetes", result["missing"])
        self.assertTrue(len(result["recommendation"]) > 0)
        self.assertIn("human recruiters conduct the final interview evaluation", result["explanation"])


    def test_validate_resume_file_security(self):
        # 1. Valid PDF file
        valid_pdf_content = b"%PDF-1.5 test resume document"
        valid_file = SimpleUploadedFile("resume.pdf", valid_pdf_content, content_type="application/pdf")
        is_valid, err, mime, fhash = validate_resume_file(valid_file)
        self.assertTrue(is_valid)
        self.assertEqual(mime, "application/pdf")
        self.assertTrue(len(fhash) == 64)

        # 2. Fake PDF with executable/malicious content
        fake_pdf = SimpleUploadedFile("malicious.pdf", b"MZ\x90\x00\x03\x00\x00\x00fake_exe", content_type="application/pdf")
        is_valid, err, _, _ = validate_resume_file(fake_pdf)
        self.assertFalse(is_valid)
        self.assertIn("does not contain a valid PDF signature", err)

        # 3. Disallowed extension
        bad_ext = SimpleUploadedFile("script.py", b"print('hello')", content_type="text/plain")
        is_valid, err, _, _ = validate_resume_file(bad_ext)
        self.assertFalse(is_valid)
        self.assertIn("Invalid file format", err)


class AuthenticationAndRBACSecurityTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            username="test_owner", password="OwnerPassword123!", role=User.Role.OWNER, is_superuser=True
        )
        self.candidate = User.objects.create_user(
            username="test_candidate", password="CandPassword123!", role=User.Role.CANDIDATE
        )
        CandidateProfile.objects.create(user=self.candidate, full_name="Test Candidate")

    def test_argon2_password_hashing(self):
        self.assertTrue(self.owner.password.startswith("argon2"))
        self.assertTrue(self.candidate.password.startswith("argon2"))

    def test_owner_dashboard_restricted_to_owner(self):
        # Candidate attempt to access owner dashboard must be denied (403 or redirect)
        self.client.login(username="test_candidate", password="CandPassword123!")
        response = self.client.get(reverse("owner_dashboard"))
        self.assertEqual(response.status_code, 403)

        # Platform owner gets access (200 OK)
        self.client.login(username="test_owner", password="OwnerPassword123!")
        response = self.client.get(reverse("owner_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Master Administration Dashboard")

    def test_owner_role_forbidden_from_public_signup(self):
        response = self.client.post(reverse("signup"), {
            "username": "hacker_owner",
            "email": "hacker@evil.com",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
            "role": "OWNER"
        })
        self.assertFalse(User.objects.filter(username="hacker_owner").exists())


class MultiTenancyIsolationTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Company A
        self.org_a = Organization.objects.create(name="Company A Tech")
        self.hr_a = User.objects.create_user(username="hr_a", password="Password123!", role=User.Role.RECRUITER)
        OrganizationMember.objects.create(organization=self.org_a, user=self.hr_a, role="HR")
        RecruiterProfile.objects.create(user=self.hr_a, organization=self.org_a, company_name=self.org_a.name)
        self.job_a = Job.objects.create(
            organization=self.org_a, recruiter=self.hr_a, title="Python Engineer A",
            company_name=self.org_a.name, required_skills="Python, Django"
        )

        # Company B
        self.org_b = Organization.objects.create(name="Company B Cloud")
        self.hr_b = User.objects.create_user(username="hr_b", password="Password123!", role=User.Role.RECRUITER)
        OrganizationMember.objects.create(organization=self.org_b, user=self.hr_b, role="HR")
        RecruiterProfile.objects.create(user=self.hr_b, organization=self.org_b, company_name=self.org_b.name)
        self.job_b = Job.objects.create(
            organization=self.org_b, recruiter=self.hr_b, title="DevOps Engineer B",
            company_name=self.org_b.name, required_skills="AWS, Docker"
        )

        # Candidate applying to Company A only
        self.candidate = User.objects.create_user(username="applicant1", password="Password123!", role=User.Role.CANDIDATE)
        CandidateProfile.objects.create(user=self.candidate, resume_consent=True)
        pdf_file = SimpleUploadedFile("resume.pdf", b"%PDF-1.5 Candidate resume text with Python", content_type="application/pdf")
        self.resume = Resume.objects.create(candidate=self.candidate, file=pdf_file, file_name="resume.pdf", extracted_text="Python")
        self.app_a = Application.objects.create(
            candidate=self.candidate, job=self.job_a, resume=self.resume, status=Application.Status.APPLIED
        )

    def test_hr_b_cannot_access_company_a_applicants(self):
        # Log in as HR of Company B and attempt to view Company A's job applicants
        self.client.login(username="hr_b", password="Password123!")
        response = self.client.get(reverse("applicants", kwargs={"pk": self.job_a.pk}))
        self.assertEqual(response.status_code, 403)

    def test_hr_b_cannot_download_company_a_candidate_resume(self):
        # HR of Company B attempts to download resume of candidate who applied to Company A
        self.client.login(username="hr_b", password="Password123!")
        response = self.client.get(reverse("download_resume", kwargs={"pk": self.resume.pk}))
        self.assertEqual(response.status_code, 403)

    def test_authorized_hr_a_can_view_and_evaluate_applicant(self):
        # HR of Company A can view applicant and update status
        self.client.login(username="hr_a", password="Password123!")
        response = self.client.get(reverse("applicants", kwargs={"pk": self.job_a.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.candidate.username)

        # Status update
        post_resp = self.client.post(reverse("update_application_status", kwargs={"pk": self.app_a.pk}), {
            "status": Application.Status.SHORTLISTED,
            "rating": "5",
            "notes": "Excellent candidate profile.",
        })
        self.assertEqual(post_resp.status_code, 302)
        self.app_a.refresh_from_db()
        self.assertEqual(self.app_a.status, Application.Status.SHORTLISTED)
        self.assertEqual(self.app_a.recruiter_rating, 5)


class ApplicationAndInterviewWorkflowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name="NexGen Labs")
        self.hr = User.objects.create_user(username="nexgen_hr", password="Password123!", role=User.Role.RECRUITER)
        OrganizationMember.objects.create(organization=self.org, user=self.hr, role="HR")
        self.job = Job.objects.create(
            organization=self.org, recruiter=self.hr, title="Full Stack Developer",
            company_name=self.org.name, required_skills="Python, React, SQL"
        )
        self.candidate = User.objects.create_user(username="dev_candidate", password="Password123!", role=User.Role.CANDIDATE)
        CandidateProfile.objects.create(user=self.candidate, resume_consent=True)
        pdf_file = SimpleUploadedFile("resume.pdf", b"%PDF-1.5 Python, React and SQL developer", content_type="application/pdf")
        self.resume = Resume.objects.create(
            candidate=self.candidate, file=pdf_file, file_name="resume.pdf",
            extracted_text="Python, React and SQL developer", is_verified=True
        )

    def test_candidate_applies_and_triggers_ai_matching(self):
        self.client.login(username="dev_candidate", password="Password123!")
        response = self.client.get(reverse("apply_job", kwargs={"pk": self.job.pk}))
        self.assertEqual(response.status_code, 302)
        
        # Verify Application and AIMatchResult created
        app = Application.objects.filter(candidate=self.candidate, job=self.job).first()
        self.assertIsNotNone(app)
        self.assertEqual(app.skill_score, 100.0)
        self.assertIsNotNone(app.ai_result)
        self.assertEqual(app.ai_result.overall_score, 100.0)

        # Verify Notification generated for HR
        notif = Notification.objects.filter(recipient=self.hr).first()
        self.assertIsNotNone(notif)
        self.assertIn("New Application", notif.title)


class ConsentAndAuditTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.candidate = User.objects.create_user(username="privacy_user", password="Password123!", role=User.Role.CANDIDATE)
        self.profile = CandidateProfile.objects.create(user=self.candidate, resume_consent=True)

    def test_consent_toggle(self):
        self.client.login(username="privacy_user", password="Password123!")
        response = self.client.post(reverse("candidate_consent_toggle"))
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.resume_consent)

    def test_gdpr_account_deletion(self):
        self.client.login(username="privacy_user", password="Password123!")
        response = self.client.post(reverse("candidate_delete_account"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(username="privacy_user").exists())
        self.assertTrue(AuditLog.objects.filter(action="ACCOUNT_DELETION_REQUESTED").exists())


class MCAMBADepartmentAndHiringPipelineTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            username="owner_user", password="Password123!", role=User.Role.OWNER, is_superuser=True
        )
        self.company_admin = User.objects.create_user(
            username="comp_admin", password="Password123!", role=User.Role.COMPANY_ADMIN
        )
        self.hr = User.objects.create_user(
            username="hr_user", password="Password123!", role=User.Role.RECRUITER
        )
        self.candidate = User.objects.create_user(
            username="mca_candidate", password="Password123!", role=User.Role.CANDIDATE
        )
        self.cand_profile = CandidateProfile.objects.create(
            user=self.candidate, full_name="MCA Graduate", education="Master of Computer Applications (MCA)"
        )
        self.org = Organization.objects.create(name="TechCorp Innovation")
        OrganizationMember.objects.create(
            organization=self.org, user=self.company_admin, role=OrganizationMember.MemberRole.ADMIN
        )
        OrganizationMember.objects.create(
            organization=self.org, user=self.hr, role=OrganizationMember.MemberRole.HR
        )

        # MCA Job
        self.mca_job = Job.objects.create(
            organization=self.org,
            recruiter=self.hr,
            title="MCA Full Stack Developer",
            company_name="TechCorp Innovation",
            department="MCA / Software Engineering",
            target_course="MCA",
            vacancies=5,
            hiring_rounds="1st Round (Screening), 2nd Round (Technical/GD), Final Round (HR)",
            required_skills="Full Stack Development, Python, Django, React, SQL",
            description="MCA Full stack role responsibilities.",
            is_active=True
        )

        # MBA Job
        self.mba_job = Job.objects.create(
            organization=self.org,
            recruiter=self.hr,
            title="MBA HR Manager & Talent Acquisition",
            company_name="TechCorp Innovation",
            department="MBA / Human Resources",
            target_course="MBA",
            vacancies=3,
            hiring_rounds="1st Round (Screening), 2nd Round (Case Study), Final Round (HR)",
            required_skills="Human Resources, Talent Acquisition, Employee Relations",
            description="MBA HR Manager role responsibilities.",
            is_active=True
        )

        # Create candidate resume and application
        pdf_file = SimpleUploadedFile("resume.pdf", b"%PDF-1.5 MCA Full Stack Developer with Python, Django, React", content_type="application/pdf")
        self.resume = Resume.objects.create(
            candidate=self.candidate, file=pdf_file, file_name="resume.pdf",
            extracted_text="Master of Computer Applications (MCA) Full Stack Developer Python, Django, React", is_verified=True
        )
        self.application = Application.objects.create(
            candidate=self.candidate,
            job=self.mca_job,
            resume=self.resume,
            status=Application.Status.ROUND_1,
            skill_score=90,
            final_score=90
        )

    def test_mca_and_mba_skill_and_education_extraction(self):
        text = "Candidate with Master of Computer Applications (MCA) skilled in Full Stack Development, React, Node.js and SQL."
        skills = extract_skills(text)
        edu = extract_education(text)
        self.assertIn("full stack development", skills)
        self.assertIn("react", skills)
        self.assertTrue(any("Mca" in e or "Computer Applications" in e for e in edu))

        mba_text = "Master of Business Administration (MBA) with expertise in Human Resources, Talent Acquisition, and Financial Modeling."
        mba_skills = extract_skills(mba_text)
        mba_edu = extract_education(mba_text)
        self.assertIn("human resources", mba_skills)
        self.assertIn("talent acquisition", mba_skills)
        self.assertIn("financial analysis", mba_skills)
        self.assertTrue(any("Mba" in e or "Business Administration" in e for e in mba_edu))

    def test_job_searching_mca_and_mba_filter(self):
        # Filter MCA
        response = self.client.get(reverse("job_list"), {"course": "MCA"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MCA Full Stack Developer")
        self.assertContains(response, "MCA DEPARTMENT HUB")

        # Filter MBA
        response_mba = self.client.get(reverse("job_list"), {"course": "MBA"})
        self.assertEqual(response_mba.status_code, 200)
        self.assertContains(response_mba, "MBA HR Manager")
        self.assertContains(response_mba, "MBA DEPARTMENT HUB")

        # Search by specific role example: Full Stack Developer
        response_role = self.client.get(reverse("job_list"), {"q": "Full Stack Developer"})
        self.assertEqual(response_role.status_code, 200)
        self.assertContains(response_role, "MCA Full Stack Developer")

    def test_owner_company_admin_and_hr_all_have_pipeline_access(self):
        # 1. Platform Owner Access
        self.client.login(username="owner_user", password="Password123!")
        res_owner = self.client.get(reverse("applicants", kwargs={"pk": self.mca_job.pk}))
        self.assertEqual(res_owner.status_code, 200)
        self.assertContains(res_owner, "Platform Owner Oversight")
        self.assertContains(res_owner, "Target: 5 Candidates")

        # 2. Company Admin Access
        self.client.login(username="comp_admin", password="Password123!")
        res_admin = self.client.get(reverse("applicants", kwargs={"pk": self.mca_job.pk}))
        self.assertEqual(res_admin.status_code, 200)
        self.assertContains(res_admin, "Company Admin Hiring Workspace")

        # 3. HR Recruiter Access
        self.client.login(username="hr_user", password="Password123!")
        res_hr = self.client.get(reverse("applicants", kwargs={"pk": self.mca_job.pk}))
        self.assertEqual(res_hr.status_code, 200)
        self.assertContains(res_hr, "HR Recruiter Hiring Workspace")

    def test_advancing_candidate_through_rounds_and_hiring_quota(self):
        self.client.login(username="hr_user", password="Password123!")
        
        # Advance from 1st Round to 2nd Round
        post_res = self.client.post(
            reverse("update_application_status", kwargs={"pk": self.application.pk}),
            {"status": Application.Status.ROUND_2, "rating": 5, "notes": "Passed 1st round aptitude test."}
        )
        self.assertEqual(post_res.status_code, 302)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.Status.ROUND_2)

        # Advance to Final Round
        self.client.post(
            reverse("update_application_status", kwargs={"pk": self.application.pk}),
            {"status": Application.Status.FINAL_ROUND, "rating": 5, "notes": "Passed technical round."}
        )
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.Status.FINAL_ROUND)

        # Finalize and HIRE candidate
        self.client.post(
            reverse("update_application_status", kwargs={"pk": self.application.pk}),
            {"status": Application.Status.HIRED, "rating": 5, "notes": "Offer letter accepted."}
        )
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.Status.HIRED)
        
        # Verify hiring vacancy progress reflects 1 hired out of 5 vacancies
        self.mca_job.refresh_from_db()
        self.assertEqual(self.mca_job.hired_count, 1)
        self.assertEqual(self.mca_job.remaining_vacancies, 4)
        self.assertEqual(self.mca_job.hiring_progress_percentage, 20)


class VacancyAndNewsV2Tests(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name="Vertex Cloud Innovations", slug="vertex-cloud")
        
        self.owner = User.objects.create_user(
            username="v2_owner",
            email="owner@vertex.com",
            password="Password123!",
            role=User.Role.OWNER,
            is_staff=True,
            is_superuser=True
        )
        self.company_admin = User.objects.create_user(
            username="v2_company_admin",
            email="admin@vertex.com",
            password="Password123!",
            role=User.Role.COMPANY_ADMIN
        )
        OrganizationMember.objects.create(
            organization=self.org,
            user=self.company_admin,
            role=OrganizationMember.MemberRole.ADMIN
        )

        self.recruiter = User.objects.create_user(
            username="v2_recruiter",
            email="recruiter@vertex.com",
            password="Password123!",
            role=User.Role.RECRUITER
        )
        OrganizationMember.objects.create(
            organization=self.org,
            user=self.recruiter,
            role=OrganizationMember.MemberRole.HR
        )
        RecruiterProfile.objects.create(
            user=self.recruiter,
            organization=self.org,
            company_name=self.org.name
        )

        self.candidate = User.objects.create_user(
            username="v2_candidate",
            email="candidate@vertex.com",
            password="Password123!",
            role=User.Role.CANDIDATE
        )
        CandidateProfile.objects.create(user=self.candidate, full_name="Alice Student")

        self.job = Job.objects.create(
            organization=self.org,
            recruiter=self.recruiter,
            title="Senior Python Backend Engineer",
            company_name=self.org.name,
            target_course=Job.TargetCourse.MCA,
            department="Cloud Engineering",
            vacancies=8,
            required_skills="Python, Django, AWS",
            description="Leading backend microservices development.",
            is_active=True,
            status=Job.Status.ACTIVE
        )

    def test_job_headcount_adjust_and_status_toggle(self):
        self.client.login(username="v2_recruiter", password="Password123!")

        # 1. Adjust headcount: delta +2
        res = self.client.post(reverse("job_headcount_adjust", kwargs={"pk": self.job.pk}), {"delta": 2})
        self.assertEqual(res.status_code, 302)
        self.job.refresh_from_db()
        self.assertEqual(self.job.vacancies, 10)

        # 2. Adjust headcount: delta -3
        self.client.post(reverse("job_headcount_adjust", kwargs={"pk": self.job.pk}), {"delta": -3})
        self.job.refresh_from_db()
        self.assertEqual(self.job.vacancies, 7)

        # 3. Toggle status: Pause job
        toggle_res = self.client.post(reverse("job_toggle_status", kwargs={"pk": self.job.pk}), {})
        self.assertEqual(toggle_res.status_code, 302)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.PAUSED)

        # 4. Toggle status: Resume job
        self.client.post(reverse("job_toggle_status", kwargs={"pk": self.job.pk}), {})
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.ACTIVE)

    def test_job_safe_deletion_and_archive(self):
        self.client.login(username="v2_recruiter", password="Password123!")

        # 1. Archive vacancy
        res = self.client.post(reverse("job_delete", kwargs={"pk": self.job.pk}), {"action": "archive"})
        self.assertEqual(res.status_code, 302)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.CLOSED)
        self.assertFalse(self.job.is_active)

        # 2. Permanent delete
        del_res = self.client.post(reverse("job_delete", kwargs={"pk": self.job.pk}), {"action": "delete"})
        self.assertEqual(del_res.status_code, 302)
        self.assertFalse(Job.objects.filter(pk=self.job.pk).exists())

    def test_owner_vacancy_moderation_and_feature(self):
        self.client.login(username="v2_owner", password="Password123!")

        # Toggle feature
        res = self.client.post(reverse("owner_toggle_job_featured", kwargs={"pk": self.job.pk}))
        self.assertEqual(res.status_code, 302)
        self.job.refresh_from_db()
        self.assertTrue(self.job.is_featured)

        # Owner delete
        del_res = self.client.post(reverse("job_delete", kwargs={"pk": self.job.pk}), {"action": "force_delete"})
        self.assertEqual(del_res.status_code, 302)
        self.assertFalse(Job.objects.filter(pk=self.job.pk).exists())

    def test_news_announcement_crud_and_permissions(self):
        # 1. Candidate cannot create news (PermissionDenied 403)
        self.client.login(username="v2_candidate", password="Password123!")
        cand_res = self.client.get(reverse("news_create"))
        self.assertEqual(cand_res.status_code, 403)

        # 2. Company admin creates company-scoped news
        self.client.login(username="v2_company_admin", password="Password123!")
        create_res = self.client.post(reverse("news_create"), {
            "title": "Vertex Cloud Campus Drive 2026",
            "category": NewsAnnouncement.Category.PLACEMENT_DRIVE,
            "target_audience": NewsAnnouncement.TargetAudience.CANDIDATES,
            "priority": NewsAnnouncement.Priority.HIGH,
            "summary": "Campus drive for MCA students.",
            "content": "Detailed schedule for the upcoming recruitment drive.",
            "is_active": True,
        })
        self.assertEqual(create_res.status_code, 302)
        news = NewsAnnouncement.objects.filter(title="Vertex Cloud Campus Drive 2026").first()
        self.assertIsNotNone(news)
        self.assertEqual(news.organization, self.org)

        # 3. View news list & detail
        list_res = self.client.get(reverse("news_list"))
        self.assertEqual(list_res.status_code, 200)
        self.assertContains(list_res, "Vertex Cloud Campus Drive 2026")

        detail_res = self.client.get(reverse("news_detail", kwargs={"slug": news.slug}))
        self.assertEqual(detail_res.status_code, 200)
        self.assertContains(detail_res, "Campus drive for MCA students.")

        # 4. Owner creates platform-wide notice
        self.client.login(username="v2_owner", password="Password123!")
        owner_news_res = self.client.post(reverse("news_create"), {
            "title": "Platform Maintenance Notice",
            "category": NewsAnnouncement.Category.SYSTEM,
            "target_audience": NewsAnnouncement.TargetAudience.ALL,
            "priority": NewsAnnouncement.Priority.URGENT,
            "summary": "Scheduled maintenance window on Sunday.",
            "content": "Platform updates will be deployed between 2 AM and 4 AM.",
            "is_active": True,
        })
        self.assertEqual(owner_news_res.status_code, 302)
        owner_news = NewsAnnouncement.objects.filter(title="Platform Maintenance Notice").first()
        self.assertIsNotNone(owner_news)
        self.assertIsNone(owner_news.organization)  # Platform-wide authority

        # 5. Owner deletes company news
        del_news_res = self.client.post(reverse("news_delete", kwargs={"pk": news.pk}))
        self.assertEqual(del_news_res.status_code, 302)
        self.assertFalse(NewsAnnouncement.objects.filter(pk=news.pk).exists())


class EnterpriseV3MasterTests(TestCase):
    """Comprehensive test suite for V3 Enterprise Architecture & AI Agents."""

    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            username="v3_owner", password="MasterPassword123!", role=User.Role.OWNER, is_superuser=True
        )
        self.company_admin = User.objects.create_user(
            username="v3_admin", password="MasterPassword123!", role=User.Role.COMPANY_ADMIN
        )
        self.recruiter = User.objects.create_user(
            username="v3_recruiter", password="MasterPassword123!", role=User.Role.RECRUITER
        )
        self.candidate = User.objects.create_user(
            username="v3_candidate", password="MasterPassword123!", role=User.Role.CANDIDATE
        )
        CandidateProfile.objects.create(user=self.candidate, full_name="Master Candidate")

        # Create pending organization
        self.org = Organization.objects.create(
            name="Apex Dynamics AI",
            slug="apex-dynamics",
            industry="Artificial Intelligence",
            verification_status=Organization.VerificationStatus.PENDING,
            is_active=False
        )
        OrganizationMember.objects.create(
            organization=self.org, user=self.company_admin, role=OrganizationMember.MemberRole.ADMIN
        )
        OrganizationMember.objects.create(
            organization=self.org, user=self.recruiter, role=OrganizationMember.MemberRole.HR
        )

    def test_owner_company_approval_and_rejection_workflow(self):
        self.client.login(username="v3_owner", password="MasterPassword123!")

        # 1. Company begins in PENDING state
        self.assertEqual(self.org.verification_status, Organization.VerificationStatus.PENDING)
        self.assertFalse(self.org.is_active)

        # 2. Owner inspects company detail
        detail_res = self.client.get(reverse("owner_company_detail", kwargs={"pk": self.org.pk}))
        self.assertEqual(detail_res.status_code, 200)
        self.assertContains(detail_res, "Apex Dynamics AI")

        # 3. Owner approves company
        approve_res = self.client.post(reverse("owner_approve_org", kwargs={"pk": self.org.pk}))
        self.assertEqual(approve_res.status_code, 302)
        self.org.refresh_from_db()
        self.assertEqual(self.org.verification_status, Organization.VerificationStatus.APPROVED)
        self.assertTrue(self.org.is_active)

        # 4. Owner rejects company with reason
        reject_res = self.client.post(
            reverse("owner_reject_org", kwargs={"pk": self.org.pk}),
            {"rejection_reason": "Incomplete business registration certificate provided."}
        )
        self.assertEqual(reject_res.status_code, 302)
        self.org.refresh_from_db()
        self.assertEqual(self.org.verification_status, Organization.VerificationStatus.REJECTED)
        self.assertFalse(self.org.is_active)
        self.assertEqual(self.org.rejection_reason, "Incomplete business registration certificate provided.")

    def test_owner_subscription_plans_and_real_mrr(self):
        self.client.login(username="v3_owner", password="MasterPassword123!")

        # 1. Create a subscription plan
        plan = SubscriptionPlan.objects.create(
            name="Enterprise Scale",
            slug="enterprise-scale",
            tier=SubscriptionPlan.Tier.ENTERPRISE,
            monthly_price=14999.00,
            annual_price=149990.00,
            currency="INR",
            max_jobs=50,
            max_resumes_per_month=5000,
            max_recruiters=20,
            ai_matching_enabled=True,
            is_active=True
        )

        # 2. Record verified and unverified payments
        Payment.objects.create(
            organization=self.org,
            plan=plan,
            amount=14999.00,
            currency="INR",
            status=Payment.Status.SUCCESS,
            transaction_id="TXN_VERIFIED_001"
        )
        Payment.objects.create(
            organization=self.org,
            plan=plan,
            amount=5000.00,
            currency="INR",
            status=Payment.Status.FAILED,
            transaction_id="TXN_FAILED_002"
        )

        # 3. Owner dashboard calculates verified MRR (excludes failed payments)
        dash_res = self.client.get(reverse("owner_dashboard"))
        self.assertEqual(dash_res.status_code, 200)
        self.assertEqual(dash_res.context["kpis"]["mrr"], 14999.00)
        self.assertContains(dash_res, "14999.00")

    def test_job_wizard_salary_validation_and_duplication(self):
        self.org.verification_status = Organization.VerificationStatus.APPROVED
        self.org.is_active = True
        self.org.save()

        self.client.login(username="v3_recruiter", password="MasterPassword123!")

        # 1. Create valid job with 6-step parameters
        create_res = self.client.post(reverse("job_create"), {
            "title": "Principal AI Architect",
            "department": "Core AI",
            "target_course": Job.TargetCourse.MCA,
            "job_type": Job.JobType.FULL_TIME,
            "workplace_type": Job.WorkplaceType.HYBRID,
            "location": "Bengaluru",
            "salary_currency": "INR",
            "salary_period": Job.SalaryPeriod.ANNUAL,
            "salary_min": 2500000,
            "salary_max": 4000000,
            "is_salary_negotiable": True,
            "display_salary_publicly": True,
            "vacancies": 3,
            "hiring_rounds": "Round 1 (Code), Round 2 (Architecture), Round 3 (Executive)",
            "experience_level": Job.ExperienceLevel.LEAD,
            "min_experience_years": 8,
            "required_skills": "Python, PyTorch, LLM, Docker, Kubernetes, Distributed Systems",
            "screening_questions": "How do you design multi-agent LLM systems?",
            "is_ai_screening_enabled": True,
            "description": "Leading enterprise AI recruitment platform architecture.",
            "status": Job.Status.ACTIVE,
            "is_active": True,
        })
        self.assertEqual(create_res.status_code, 302)
        job = Job.objects.filter(title="Principal AI Architect").first()
        self.assertIsNotNone(job)
        self.assertEqual(job.vacancies, 3)
        self.assertEqual(job.salary_currency, "INR")

        # 2. Test duplicate job endpoint
        dup_res = self.client.post(reverse("job_duplicate", kwargs={"pk": job.pk}))
        self.assertEqual(dup_res.status_code, 302)
        copy_job = Job.objects.filter(title="Copy of Principal AI Architect").first()
        self.assertIsNotNone(copy_job)
        self.assertEqual(copy_job.vacancies, 3)
        self.assertEqual(copy_job.min_experience_years, 8)

        # 3. Validation: salary_min cannot exceed salary_max
        from recruitment.forms import JobForm
        invalid_form = JobForm(data={
            "title": "Bad Job",
            "target_course": "MCA",
            "vacancies": 1,
            "salary_min": 500000,
            "salary_max": 200000,  # Max less than Min
            "required_skills": "Python",
            "description": "Test",
            "status": "ACTIVE",
        })
        self.assertFalse(invalid_form.is_valid())
        self.assertIn("salary_max", invalid_form.errors)

    def test_modular_7_agent_ai_recruitment_architecture(self):
        # Agent 1: DataQualityAgent
        is_clean, quality_score, issues = DataQualityAgent.check_text_integrity(
            "Experienced candidate profile statement. Official Contact email: engineer@example.com, Phone: +1-555-019-2834. "
            "Extensive background in scalable software design, distributed architectures, continuous integration pipelines, "
            "and enterprise cloud systems."
        )
        self.assertTrue(is_clean)
        self.assertGreaterEqual(quality_score, 80)

        # Agent 2: ResumeParsingAgent
        resume_sample = (
            "Senior MCA graduate with 6.5 years of experience in enterprise development. "
            "Master of Computer Applications (MCA) from NIT Trichy. "
            "Proficient in Python, Django, PostgreSQL, Docker, Kubernetes, AWS, Machine Learning."
        )
        skills = ResumeParsingAgent.extract_skills(resume_sample)
        self.assertIn("python", skills)
        self.assertIn("django", skills)
        self.assertIn("postgresql", skills)
        self.assertIn("docker", skills)
        self.assertIn("kubernetes", skills)
        self.assertIn("machine learning", skills)

        edu = ResumeParsingAgent.extract_education(resume_sample)
        self.assertTrue(any("Mca" in e or "Master Of Computer Applications" in e for e in edu))

        # Agent 3: JobUnderstandingAgent
        reqs = JobUnderstandingAgent.decompose_requirements(
            ["Python", "Django", "PostgreSQL", "Docker", "Rust"],
            job_description="Mandatory: Python and Django are core requirements. Nice to have: Rust."
        )
        self.assertIn("python", reqs["mandatory_skills"])
        self.assertIn("django", reqs["mandatory_skills"])
        self.assertIn("rust", reqs["preferred_skills"])

        # Agent 4: SkillMatchingAgent
        match_data = SkillMatchingAgent.match(
            candidate_skills=skills,
            required_skills=["python", "django", "postgresql", "rust", "golang"]
        )
        self.assertEqual(match_data["matched"], ["django", "postgresql", "python"])
        self.assertEqual(match_data["missing"], ["golang", "rust"])
        self.assertEqual(match_data["skill_score"], 60.0)

        # Agent 5: SemanticMatchingAgent
        sim_score, note = SemanticMatchingAgent.calculate_similarity(
            "Backend engineer designing high-scale REST APIs with Python and PostgreSQL.",
            "Seeking Python backend engineer with database optimization and REST API skills."
        )
        self.assertGreater(sim_score, 0.0)

        # Agent 6: CandidateExplanationAgent
        report = CandidateExplanationAgent.generate_explanation(
            skill_data=match_data,
            semantic_score=sim_score,
            semantic_note=note,
            job_title="Senior Backend Engineer"
        )
        self.assertIn("Candidate can increase match alignment", report["recommendation"])
        self.assertIn("Evaluated 5 required competencies", report["explanation"])
        self.assertTrue(report["final_score"] > 0)

        # Agent 7: RecruitmentAssistantAgent
        questions = RecruitmentAssistantAgent.generate_interview_questions(
            job_title="Senior Backend Engineer",
            matched_skills=match_data["matched"],
            missing_skills=match_data["missing"]
        )
        self.assertGreaterEqual(len(questions), 3)
        self.assertTrue(any("Django" in q or "Python" in q for q in questions))


class StartupPlatformModulesTests(TestCase):
    """Exhaustive tests for new startup platform modules: Companies, Legal, Bookmarks, Moderation."""

    def setUp(self):
        self.client = Client()
        self.owner_user = User.objects.create_superuser(
            username="test_owner", email="owner@hirenexa.internal", password="OwnerPassword123!"
        )
        self.owner_user.role = User.Role.OWNER
        self.owner_user.save()

        self.candidate_user = User.objects.create_user(
            username="test_cand", email="candidate@test.com", password="CandidatePass123!", role=User.Role.CANDIDATE
        )
        self.candidate_profile = CandidateProfile.objects.create(
            user=self.candidate_user, full_name="Candidate Tester", skills="Python, Django, PostgreSQL"
        )

        self.recruiter_user = User.objects.create_user(
            username="test_rec", email="recruiter@company.com", password="RecruiterPass123!", role=User.Role.RECRUITER
        )
        self.org = Organization.objects.create(name="NexGen Software Corp", verification_status="APPROVED")
        OrganizationMember.objects.create(organization=self.org, user=self.recruiter_user, role="HR")
        self.recruiter_profile = RecruiterProfile.objects.create(user=self.recruiter_user, organization=self.org)

        self.job = Job.objects.create(
            organization=self.org,
            recruiter=self.recruiter_user,
            title="Senior Python Backend Developer",
            company_name=self.org.name,
            required_skills="Python, Django, SQL",
            description="Build scalable APIs and distributed systems.",
            vacancies=5
        )

        # Upload a dummy resume
        dummy_pdf = SimpleUploadedFile("my_resume.pdf", b"%PDF-1.4\nTest Resume Content\nPython Django SQL", content_type="application/pdf")
        self.resume = Resume.objects.create(
            candidate=self.candidate_user, file=dummy_pdf, file_name="my_resume.pdf", extracted_text="Python Django SQL"
        )
        self.app = Application.objects.create(
            candidate=self.candidate_user, job=self.job, resume=self.resume, status=Application.Status.APPLIED
        )

    def test_companies_directory_public_access(self):
        """Public visitors can browse verified companies with active vacancy counts."""
        resp = self.client.get(reverse("companies_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "NexGen Software Corp")
        self.assertContains(resp, "1 Active Job")

    def test_career_resources_and_legal_pages(self):
        """Career resources, Terms of Service, and Privacy Policy load cleanly."""
        for url_name in ["career_resources", "terms", "privacy", "resume_analyzer"]:
            resp = self.client.get(reverse(url_name))
            self.assertEqual(resp.status_code, 200)

    def test_candidate_save_and_unsave_job(self):
        """Candidate can bookmark and remove jobs from saved list."""
        from recruitment.models import SavedJob
        self.client.login(username="test_cand", password="CandidatePass123!")

        # 1. Bookmark job
        save_resp = self.client.post(reverse("toggle_save_job", args=[self.job.pk]), follow=True)
        self.assertEqual(save_resp.status_code, 200)
        self.assertTrue(SavedJob.objects.filter(candidate=self.candidate_user, job=self.job).exists())

        # 2. View saved jobs page
        list_resp = self.client.get(reverse("candidate_saved_jobs"))
        self.assertEqual(list_resp.status_code, 200)
        self.assertContains(list_resp, "Senior Python Backend Developer")

        # 3. Un-bookmark job
        unsave_resp = self.client.post(reverse("toggle_save_job", args=[self.job.pk]), follow=True)
        self.assertEqual(unsave_resp.status_code, 200)
        self.assertFalse(SavedJob.objects.filter(candidate=self.candidate_user, job=self.job).exists())

    def test_candidate_withdraw_application(self):
        """Candidate can withdraw an active pending job application."""
        self.client.login(username="test_cand", password="CandidatePass123!")
        withdraw_resp = self.client.post(reverse("withdraw_application", args=[self.app.pk]), follow=True)
        self.assertEqual(withdraw_resp.status_code, 200)
        self.app.refresh_from_db()
        self.assertEqual(self.app.status, Application.Status.WITHDRAWN)

    def test_report_suspicious_listing_and_owner_resolve(self):
        """User reports suspicious listing; platform owner resolves it."""
        from recruitment.models import UserReport
        self.client.login(username="test_cand", password="CandidatePass123!")

        # File report
        report_resp = self.client.post(reverse("report_listing"), {
            "target_id": str(self.job.id),
            "target_title": self.job.title,
            "report_type": "JOB_LISTING",
            "reason": "Suspicious listing asking for off-platform payment."
        }, follow=True)
        self.assertEqual(report_resp.status_code, 200)

        report = UserReport.objects.filter(target_id=str(self.job.id)).first()
        self.assertIsNotNone(report)
        self.assertEqual(report.status, UserReport.Status.PENDING)

        # Owner resolves report
        self.client.login(username="test_owner", password="OwnerPassword123!")
        resolve_resp = self.client.post(reverse("owner_resolve_report", args=[report.pk]), {
            "action": "RESOLVE",
            "admin_notes": "Reviewed and verified opening is authentic."
        }, follow=True)
        self.assertEqual(resolve_resp.status_code, 200)
        report.refresh_from_db()
        self.assertEqual(report.status, UserReport.Status.RESOLVED)

    def test_interview_scheduling_rescheduling_and_cancellation(self):
        """HR recruiter can schedule, reschedule, and cancel candidate interviews."""
        self.client.login(username="test_rec", password="RecruiterPass123!")

        # 1. Schedule Interview
        sched_resp = self.client.post(reverse("schedule_interview", args=[self.app.pk]), {
            "round_name": "Technical Architecture Round",
            "scheduled_at": "2026-12-01 14:00:00",
            "mode": "ONLINE",
            "meeting_link": "https://meet.google.com/abc-defg-hij",
            "notes": "Be ready to explain system architecture tradeoffs."
        }, follow=True)
        self.assertEqual(sched_resp.status_code, 200)

        interview = Interview.objects.filter(application=self.app).first()
        self.assertIsNotNone(interview)
        self.assertEqual(interview.status, Interview.Status.SCHEDULED)

        # 2. Reschedule Interview
        resched_resp = self.client.post(reverse("reschedule_interview", args=[interview.pk]), {
            "round_name": "Technical Architecture Round (Rescheduled)",
            "scheduled_at": "2026-12-02 15:00:00",
            "mode": "ONLINE",
            "meeting_link": "https://meet.google.com/abc-defg-hij",
            "notes": "Updated timing."
        }, follow=True)
        self.assertEqual(resched_resp.status_code, 200)
        interview.refresh_from_db()
        self.assertEqual(interview.status, Interview.Status.RESCHEDULED)

        # 3. Cancel Interview
        cancel_resp = self.client.post(reverse("cancel_interview", args=[interview.pk]), follow=True)
        self.assertEqual(cancel_resp.status_code, 200)
        interview.refresh_from_db()
        self.assertEqual(interview.status, Interview.Status.CANCELLED)

    def test_in_app_notifications_center(self):
        """User can view and mark notifications as read."""
        Notification.objects.create(
            recipient=self.candidate_user,
            title="Interview Scheduled",
            message="Your technical interview has been scheduled.",
            notification_type=Notification.Type.INTERVIEW
        )
        self.client.login(username="test_cand", password="CandidatePass123!")

        resp = self.client.get(reverse("notifications_view"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Interview Scheduled")

        # Mark all read
        mark_resp = self.client.post(reverse("mark_all_notifications_read"), follow=True)
        self.assertEqual(mark_resp.status_code, 200)
        self.assertEqual(Notification.objects.filter(recipient=self.candidate_user, is_read=False).count(), 0)


class APISecurityAndPermissionTests(TestCase):
    """
    Tests REST API authorization boundaries:
    - Candidate cannot mutate Organization or Job (HTTP 403)
    - Org Admin can mutate their own Organization
    - Recruiter can mutate their own Job
    - Cross-tenant mutations are blocked
    """
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner_api", email="owner@api.com", password="Password123!", role=User.Role.OWNER, is_superuser=True
        )
        self.company_admin = User.objects.create_user(
            username="admin_api", email="admin@org1.com", password="Password123!", role=User.Role.COMPANY_ADMIN
        )
        self.other_admin = User.objects.create_user(
            username="other_api", email="admin@org2.com", password="Password123!", role=User.Role.COMPANY_ADMIN
        )
        self.recruiter = User.objects.create_user(
            username="recruiter_api", email="hr@org1.com", password="Password123!", role=User.Role.RECRUITER
        )
        self.candidate = User.objects.create_user(
            username="cand_api", email="cand@edu.com", password="Password123!", role=User.Role.CANDIDATE
        )

        self.org1 = Organization.objects.create(name="Alpha Corp", is_active=True)
        self.org2 = Organization.objects.create(name="Beta Corp", is_active=True)

        OrganizationMember.objects.create(organization=self.org1, user=self.company_admin, role=OrganizationMember.MemberRole.ADMIN)
        OrganizationMember.objects.create(organization=self.org1, user=self.recruiter, role=OrganizationMember.MemberRole.HR)
        OrganizationMember.objects.create(organization=self.org2, user=self.other_admin, role=OrganizationMember.MemberRole.ADMIN)

        self.job1 = Job.objects.create(
            title="Backend Engineer", organization=self.org1, recruiter=self.recruiter,
            vacancies=3, status=Job.Status.ACTIVE, is_active=True
        )

    def test_candidate_cannot_delete_or_update_organization(self):
        self.client.force_login(self.candidate)
        resp = self.client.patch(f"/api/v1/organizations/{self.org1.id}/", {"name": "Hacked Org"}, content_type="application/json")
        self.assertEqual(resp.status_code, 403)
        resp_del = self.client.delete(f"/api/v1/organizations/{self.org1.id}/")
        self.assertEqual(resp_del.status_code, 403)

    def test_cross_org_admin_cannot_modify_other_organization(self):
        self.client.force_login(self.other_admin)
        resp = self.client.patch(f"/api/v1/organizations/{self.org1.id}/", {"name": "Tampered"}, content_type="application/json")
        self.assertEqual(resp.status_code, 403)

    def test_own_org_admin_can_update_organization(self):
        self.client.force_login(self.company_admin)
        resp = self.client.patch(f"/api/v1/organizations/{self.org1.id}/", {"name": "Alpha Corp Updated"}, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.org1.refresh_from_db()
        self.assertEqual(self.org1.name, "Alpha Corp Updated")

    def test_candidate_cannot_create_job_via_api(self):
        self.client.force_login(self.candidate)
        resp = self.client.post("/api/v1/jobs/", {
            "title": "Malicious Job", "vacancies": 5, "description": "Fake job"
        }, content_type="application/json")
        self.assertEqual(resp.status_code, 403)

    def test_recruiter_can_create_job_via_api(self):
        self.client.force_login(self.recruiter)
        resp = self.client.post("/api/v1/jobs/", {
            "title": "API Job Posting", "vacancies": 2, "description": "Real job"
        }, content_type="application/json")
        self.assertEqual(resp.status_code, 201)





