import json
from decimal import Decimal
from django.test import TestCase, Client
from django.utils import timezone
from accounts.models import User
from recruitment.models import (
    Organization,
    Job,
    Application,
    CandidateProfile,
    CandidateSkill,
    ProjectPortfolio,
    CompanyVerificationDocument,
)
from recruitment.career_assistant_service import CareerAssistantService
from recruitment.market_intelligence_service import SkillMarketIntelligenceService
from recruitment.job_discovery_service import IntelligentJobDiscoveryEngine
from recruitment.company_trust_service import CompanyTrustService
from recruitment.skill_passport_service import SkillPassportService
from recruitment.recruiter_intelligence_service import RecruiterIntelligenceService
from recruitment.location_service import LocationDiscoveryService
from recruitment.notification_engine import PersonalizedNotificationEngine
from recruitment.data_intelligence_service import DataIntelligenceCenter

try:
    from assessments.exam_coach_service import ExamCoachService
    from assessments.learning_path_service import LearningPathService
    from assessments.models import Subject, Topic, Question, ExamAttempt, Result
except ImportError:
    ExamCoachService = None
    LearningPathService = None
    Subject = None
    Topic = None
    Question = None
    ExamAttempt = None
    Result = None


class AdvancedProductInnovationTests(TestCase):
    """
    Automated integration and unit test suite verifying the 11 Advanced
    Product Innovation & Ecosystem Services for HireNexa.
    """

    @classmethod
    def setUpTestData(cls):
        # 1. Create Verified Employer Organization
        cls.org = Organization.objects.create(
            name="Apex AI Technologies",
            industry="Artificial Intelligence & Cloud",
            website="https://apexai.example.com",
            location="Bhubaneswar, Odisha",
            city="Bhubaneswar",
            state="Odisha",
            district="Khordha",
            country="India",
            pin_code="751024",
            building_name="Apex Innovation Tower",
            street_address="Infocity Road, Patia",
            formatted_address="Apex Innovation Tower, Infocity Road, Patia, Bhubaneswar, Odisha - 751024",
            latitude=Decimal("20.3533000"),
            longitude=Decimal("85.8266000"),
            verification_status=Organization.VerificationStatus.APPROVED,
        )

        # 2. Add approved verification document
        CompanyVerificationDocument.objects.create(
            organization=cls.org,
            document_type="Certificate of Incorporation",
            file="company_verification_docs/test_cert.pdf",
            status=CompanyVerificationDocument.Status.APPROVED,
        )

        # 3. Create Users (Recruiter, Candidate, Owner)
        cls.recruiter_user = User.objects.create_user(
            username="recruiter_sneha",
            email="sneha@apexai.example.com",
            password="SecurePassword123!",
            role=User.Role.RECRUITER,
            first_name="Sneha",
            last_name="Mohanty",
        )

        cls.candidate_user = User.objects.create_user(
            username="candidate_rohan",
            email="rohan.cs@example.com",
            password="SecurePassword123!",
            role=User.Role.CANDIDATE,
            first_name="Rohan",
            last_name="Das",
        )

        cls.owner_user = User.objects.create_user(
            username="platform_owner",
            email="owner@hirenexa.internal",
            password="SecurePassword123!",
            role=User.Role.OWNER,
            is_staff=True,
            is_superuser=True,
        )

        # 4. Candidate Profile & Skills
        cls.candidate_profile = CandidateProfile.objects.create(
            user=cls.candidate_user,
            full_name="Rohan Das",
            headline="Python Backend Engineer | Django & Cloud",
            education="B.Tech Computer Science",
            university="IIT Bhubaneswar",
            cgpa="8.9 / 10",
            location="Bhubaneswar",
            preferred_locations=["Bhubaneswar", "Bengaluru"],
            preferred_work_mode="HYBRID",
            skills="Python, Django, PostgreSQL, Git",
            github_url="https://github.com/rohandas",
            linkedin_url="https://linkedin.com/in/rohandas",
            bio="Passionate about designing scalable distributed APIs.",
        )

        CandidateSkill.objects.create(
            candidate=cls.candidate_user,
            name="Python",
            proficiency=CandidateSkill.Proficiency.ADVANCED,
            years_of_experience=2.0,
            verified=True,
        )
        CandidateSkill.objects.create(
            candidate=cls.candidate_user,
            name="Django",
            proficiency=CandidateSkill.Proficiency.ADVANCED,
            years_of_experience=1.5,
            verified=True,
        )

        # 5. Candidate Portfolio Project
        ProjectPortfolio.objects.create(
            candidate=cls.candidate_user,
            project_name="Distributed Task Scheduler",
            description="Asynchronous worker queue system using Python and Redis.",
            category=ProjectPortfolio.Category.WEB,
            technologies="Python, Django, Redis, Docker",
            github_url="https://github.com/rohandas/scheduler",
            live_demo_url="https://scheduler-demo.example.com",
        )

        # 6. Create Active Jobs
        cls.job1 = Job.objects.create(
            organization=cls.org,
            recruiter=cls.recruiter_user,
            title="Backend Python Engineer",
            company_name="Apex AI Technologies",
            department="Cloud Services",
            target_course=Job.TargetCourse.ALL,
            vacancies=4,
            job_type=Job.JobType.FULL_TIME,
            experience_level=Job.ExperienceLevel.MID,
            min_experience_years=1,
            location="Bhubaneswar",
            city="Bhubaneswar",
            state="Odisha",
            workplace_type=Job.WorkplaceType.HYBRID,
            description="Build scalable microservices with Python, Django, PostgreSQL, and Docker.",
            required_skills="Python, Django, PostgreSQL, Docker, Redis",
            salary_min=Decimal("800000"),
            salary_max=Decimal("1400000"),
            display_salary_publicly=True,
            status=Job.Status.ACTIVE,
            is_active=True,
        )

        cls.job2 = Job.objects.create(
            organization=cls.org,
            recruiter=cls.recruiter_user,
            title="Full Stack MCA Specialist",
            company_name="Apex AI Technologies",
            department="Web Apps",
            target_course=Job.TargetCourse.MCA,
            vacancies=2,
            job_type=Job.JobType.FULL_TIME,
            experience_level=Job.ExperienceLevel.ENTRY,
            min_experience_years=0,
            location="Remote",
            workplace_type=Job.WorkplaceType.REMOTE,
            description="React frontend and Python backend specialist.",
            required_skills="React, JavaScript, Python, REST API",
            status=Job.Status.ACTIVE,
            is_active=True,
        )

    def setUp(self):
        self.client = Client()

    # --------------------------------------------------------------------------
    # 1. ADVANCED AI CAREER ASSISTANT TESTS
    # --------------------------------------------------------------------------
    def test_career_assistant_service(self):
        context = CareerAssistantService.get_candidate_context(self.candidate_user)
        self.assertEqual(context["full_name"], "Rohan Das")
        self.assertIn("Python", context["user_skills"])
        self.assertEqual(context["portfolio_count"], 1)

        gaps = CareerAssistantService.analyze_skill_gaps(self.candidate_user, target_role="Backend Python Engineer")
        self.assertGreater(gaps["sample_jobs_analyzed"], 0)
        self.assertIsInstance(gaps["missing_skills"], list)

        jobs = CareerAssistantService.recommend_jobs_with_reasoning(self.candidate_user, limit=2)
        self.assertGreaterEqual(len(jobs), 1)
        self.assertIn("skill match", jobs[0]["reasoning"].lower())

        projects = CareerAssistantService.generate_project_suggestions(self.candidate_user)
        self.assertGreaterEqual(len(projects), 1)

        tracking = CareerAssistantService.track_career_development(self.candidate_user)
        self.assertGreater(tracking["readiness_score"], 0)

    def test_career_assistant_view(self):
        self.client.force_login(self.candidate_user)
        resp = self.client.get("/candidate/career-assistant/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "AI Career Assistant")
        self.assertContains(resp, "Placement Readiness Score")

    # --------------------------------------------------------------------------
    # 2. AI SKILL MARKET INTELLIGENCE TESTS
    # --------------------------------------------------------------------------
    def test_skill_market_intelligence_service(self):
        intel = SkillMarketIntelligenceService.get_market_intelligence(days=90)
        self.assertGreaterEqual(intel["metadata"]["sample_size"], 2)
        self.assertIn("statistical_disclaimer", intel["metadata"])

        # Check top skills
        skill_names = [s["skill"] for s in intel["frequently_requested_skills"]]
        self.assertIn("Python", skill_names)

        # Check API endpoint
        resp = self.client.get("/api/v1/market-intelligence/?days=90")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("frequently_requested_skills", data)

    def test_market_intelligence_view(self):
        resp = self.client.get("/market-intelligence/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Skill Market Intelligence")
        self.assertContains(resp, "Data Transparency Disclosure")

    # --------------------------------------------------------------------------
    # 3. INTELLIGENT JOB DISCOVERY TESTS
    # --------------------------------------------------------------------------
    def test_job_discovery_service(self):
        results = IntelligentJobDiscoveryEngine.discover_jobs(
            user=self.candidate_user,
            preferences_override={"preferred_work_mode": "HYBRID", "preferred_locations": ["Bhubaneswar"]},
            limit=5
        )
        self.assertGreaterEqual(results["total_matches"], 1)
        top_match = results["recommendations"][0]
        self.assertGreater(top_match["total_score"], 50.0)
        self.assertIn("breakdown", top_match)
        self.assertIn("reasons", top_match)

    def test_job_discovery_view(self):
        resp = self.client.get("/jobs/discovery/?work_mode=HYBRID&city=Bhubaneswar")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Intelligent Job Discovery")
        self.assertContains(resp, "Suitability Dimensions")

    # --------------------------------------------------------------------------
    # 4. COMPANY TRUST AND VERIFICATION TESTS
    # --------------------------------------------------------------------------
    def test_company_trust_service(self):
        trust = CompanyTrustService.evaluate_company_trust(self.org)
        self.assertGreaterEqual(trust["trust_score"], 70)
        self.assertTrue(trust["is_fully_verified"])
        self.assertEqual(trust["tier_label"], "HireNexa Verified Employer")
        self.assertGreaterEqual(len(trust["badges"]), 2)

    def test_company_trust_view(self):
        resp = self.client.get(f"/companies/{self.org.id}/trust/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Company Trust & Verification")
        self.assertContains(resp, "Apex AI Technologies")

    def test_report_suspicious_job(self):
        self.client.force_login(self.candidate_user)
        resp = self.client.post(
            f"/jobs/{self.job1.id}/report/",
            {"reason": "Suspicious listing", "details": "Testing candidate safety"}
        )
        self.assertEqual(resp.status_code, 302)

    # --------------------------------------------------------------------------
    # 5. AI EXAMINATION COACH TESTS
    # --------------------------------------------------------------------------
    def test_exam_coach_view(self):
        self.client.force_login(self.candidate_user)
        resp = self.client.get("/assessments/coach/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "AI Examination Coach")

    def test_exam_coach_practice_view(self):
        self.client.force_login(self.candidate_user)
        resp = self.client.get("/assessments/coach/practice/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Adaptive Practice Drill")

    # --------------------------------------------------------------------------
    # 6. SMART LEARNING PATH TESTS
    # --------------------------------------------------------------------------
    def test_learning_paths_service_and_view(self):
        paths = LearningPathService.list_paths(user=self.candidate_user)
        self.assertGreaterEqual(len(paths), 2)

        path_detail = LearningPathService.get_learning_path("python-backend-engineer", user=self.candidate_user)
        self.assertIsNotNone(path_detail)
        self.assertEqual(path_detail["total_milestones"], 8)

        resp = self.client.get("/learning-paths/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Smart Learning Paths")

        resp_detail = self.client.get("/learning-paths/python-backend-engineer/")
        self.assertEqual(resp_detail.status_code, 200)
        self.assertContains(resp_detail, "Python Enterprise Backend Engineer")

    # --------------------------------------------------------------------------
    # 7. HIRENEXA PROFESSIONAL SKILL PASSPORT TESTS
    # --------------------------------------------------------------------------
    def test_skill_passport_service(self):
        passport = SkillPassportService.generate_passport(self.candidate_user)
        self.assertTrue(passport["passport_id"].startswith("HNX-PASS-"))
        self.assertTrue(len(passport["integrity_hash"]) == 64)
        self.assertIn("verified_portfolio_projects", passport["verified_achievements"])
        self.assertEqual(len(passport["verified_achievements"]["verified_portfolio_projects"]), 1)

    def test_candidate_passport_view(self):
        self.client.force_login(self.candidate_user)
        resp = self.client.get("/candidate/passport/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Professional Skill Passport")
        self.assertContains(resp, "Independently Verified Achievements")

    def test_public_passport_verify_view(self):
        passport = SkillPassportService.generate_passport(self.candidate_user)
        resp = self.client.get(f"/passport/{passport['passport_id']}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Authenticated Employer Verification View")
        self.assertContains(resp, passport["passport_id"])

    # --------------------------------------------------------------------------
    # 8. RECRUITER INTELLIGENCE DASHBOARD TESTS
    # --------------------------------------------------------------------------
    def test_recruiter_intelligence_service_and_view(self):
        overview = RecruiterIntelligenceService.get_pipeline_overview(self.recruiter_user)
        self.assertIn("funnel", overview)
        self.assertIn("ai_governance_disclaimer", overview)

        self.client.force_login(self.recruiter_user)
        resp = self.client.get("/hr/intelligence/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Recruiter Intelligence Dashboard")
        self.assertContains(resp, "Applicant Pipeline Funnel Conversion")

    # --------------------------------------------------------------------------
    # 9. HIRENEXA LOCATION DISCOVERY TESTS
    # --------------------------------------------------------------------------
    def test_location_discovery_service(self):
        # Coordinates near Bhubaneswar
        result = LocationDiscoveryService.discover_nearby_jobs(
            candidate_lat=20.3500, candidate_lon=85.8200, max_distance_km=25.0
        )
        self.assertGreaterEqual(result["total_found"], 1)
        nearest = result["jobs"][0]
        self.assertIsNotNone(nearest["distance_km"])
        self.assertLess(nearest["distance_km"], 10.0)

    def test_location_discovery_view(self):
        resp = self.client.get("/jobs/nearby/?city=Bhubaneswar&mode=HYBRID")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "HireNexa Location Discovery")
        self.assertContains(resp, "Apex AI Technologies")

    # --------------------------------------------------------------------------
    # 10. NOTIFICATION ENGINE TESTS
    # --------------------------------------------------------------------------
    def test_notification_engine(self):
        res = PersonalizedNotificationEngine.notify_relevant_job(
            user=self.candidate_user,
            job_title="Senior Python Architect",
            company_name="Apex AI Technologies",
            match_pct=95,
            job_id=self.job1.id,
        )
        self.assertTrue(res["dispatched"])
        self.assertTrue(res["inapp_created"])

        self.client.force_login(self.candidate_user)
        resp = self.client.get("/notifications/center/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Senior Python Architect")

    # --------------------------------------------------------------------------
    # 11. DATA INTELLIGENCE CENTER TESTS
    # --------------------------------------------------------------------------
    def test_data_intelligence_center(self):
        intel = DataIntelligenceCenter.get_full_platform_intelligence()
        self.assertIn("candidate_activity", intel)
        self.assertIn("recruitment_pipeline", intel)
        self.assertIn("question_bank_quality", intel)

        self.client.force_login(self.owner_user)
        resp = self.client.get("/owner/intelligence/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Data Intelligence Center")
        self.assertContains(resp, "EXECUTIVE DATA PLATFORM")
