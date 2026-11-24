from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError

from accounts.models import User
from recruitment.models import (
    Country, State, District, City, Area, PinCode,
    CandidateProfile, RecruiterProfile, Organization, OrganizationMember,
    Job, Application, Resume, ProjectPortfolio, ProjectFile
)
from core.supabase_service import SupabaseService


class LocationAutocompleteAndHierarchyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.country = Country.objects.create(name="India", iso2="IN", iso3="IND", phone_code="+91")
        cls.state_ka = State.objects.create(country=cls.country, name="Karnataka", code="KA", type="state")
        cls.dist_blr = District.objects.create(state=cls.state_ka, name="Bangalore Urban")
        cls.city_blr = City.objects.create(state=cls.state_ka, district=cls.dist_blr, name="Bengaluru", tier=1, is_metro=True)
        cls.area_wf = Area.objects.create(city=cls.city_blr, name="Whitefield")
        cls.pin_wf = PinCode.objects.create(state=cls.state_ka, city=cls.city_blr, area=cls.area_wf, pin_code="560066")

        cls.state_od = State.objects.create(country=cls.country, name="Odisha", code="OD", type="state")
        cls.dist_khd = District.objects.create(state=cls.state_od, name="Khurda")
        cls.city_bbsr = City.objects.create(state=cls.state_od, district=cls.dist_khd, name="Bhubaneswar", tier=2, is_metro=False)

    def setUp(self):
        self.client = Client()

    def test_location_autocomplete_pin_code(self):
        resp = self.client.get(reverse('location_autocomplete'), {'q': '560066'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(data['count'], 1)
        res = data['results'][0]
        self.assertEqual(res['type'], 'pin_code')
        self.assertEqual(res['value'], '560066')
        self.assertIn('Bengaluru', res['subtext'])
        self.assertIn('Karnataka', res['subtext'])

    def test_location_autocomplete_area(self):
        resp = self.client.get(reverse('location_autocomplete'), {'q': 'Whitefield'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(data['count'], 1)
        matched = [r for r in data['results'] if r['value'] == 'Whitefield']
        self.assertTrue(len(matched) > 0)
        self.assertEqual(matched[0]['type'], 'area')

    def test_location_autocomplete_city(self):
        resp = self.client.get(reverse('location_autocomplete'), {'q': 'Bengaluru'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        matched = [r for r in data['results'] if r['value'] == 'Bengaluru']
        self.assertTrue(len(matched) > 0)
        self.assertEqual(matched[0]['type'], 'city')

    def test_location_autocomplete_modes(self):
        # Test Remote
        resp = self.client.get(reverse('location_autocomplete'), {'q': 'Remote'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        matched = [r for r in data['results'] if r['value'] == 'Remote']
        self.assertTrue(len(matched) > 0)
        self.assertEqual(matched[0]['type'], 'mode')

        # Test All India
        resp2 = self.client.get(reverse('location_autocomplete'), {'q': 'All India'})
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        matched2 = [r for r in data2['results'] if r['value'] == 'All India']
        self.assertTrue(len(matched2) > 0)
        self.assertEqual(matched2[0]['type'], 'mode')

    def test_location_hierarchy_api(self):
        resp = self.client.get(reverse('location_hierarchy'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertGreaterEqual(len(data['countries']), 1)
        self.assertGreaterEqual(len(data['states']), 2)


class JobSearchLocationFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.recruiter_user = User.objects.create_user(
            username="recruiter_loc", password="TestPassword123!", role=User.Role.RECRUITER
        )
        cls.org = Organization.objects.create(name="Tech Innovations India", industry="Software")
        OrganizationMember.objects.create(
            organization=cls.org, user=cls.recruiter_user, role=OrganizationMember.MemberRole.ADMIN
        )
        cls.recruiter_prof = RecruiterProfile.objects.create(
            user=cls.recruiter_user, company_name="Tech Innovations India"
        )

        cls.job_blr = Job.objects.create(
            title="Senior Python Backend Architect",
            organization=cls.org,
            recruiter=cls.recruiter_user,
            company_name="Tech Innovations India",
            location="Bengaluru, Karnataka",
            workplace_type=Job.WorkplaceType.HYBRID,
            required_skills="python, django, postgresql",
            description="Leading backend systems in Bengaluru.",
            status=Job.Status.ACTIVE
        )
        cls.job_remote = Job.objects.create(
            title="Lead React Frontend Engineer",
            organization=cls.org,
            recruiter=cls.recruiter_user,
            company_name="Tech Innovations India",
            location="Remote / Anywhere",
            workplace_type=Job.WorkplaceType.REMOTE,
            required_skills="react, typescript",
            description="Remote frontend role across India.",
            status=Job.Status.ACTIVE
        )
        cls.job_bbsr = Job.objects.create(
            title="Full Stack Cloud Specialist",
            organization=cls.org,
            recruiter=cls.recruiter_user,
            company_name="Tech Innovations India",
            location="Bhubaneswar, Odisha",
            workplace_type=Job.WorkplaceType.ONSITE,
            required_skills="python, react",
            description="On-site cloud operations at Bhubaneswar.",
            status=Job.Status.ACTIVE
        )

    def setUp(self):
        self.client = Client()

    def test_filter_jobs_by_city(self):
        resp = self.client.get(reverse('job_list'), {'location': 'Bengaluru'})
        self.assertEqual(resp.status_code, 200)
        jobs = list(resp.context['jobs'])
        titles = [j.title for j in jobs]
        self.assertIn("Senior Python Backend Architect", titles)
        self.assertNotIn("Full Stack Cloud Specialist", titles)

    def test_filter_jobs_by_remote(self):
        resp = self.client.get(reverse('job_list'), {'location': 'Remote'})
        self.assertEqual(resp.status_code, 200)
        jobs = list(resp.context['jobs'])
        titles = [j.title for j in jobs]
        self.assertIn("Lead React Frontend Engineer", titles)

    def test_filter_jobs_all_india(self):
        resp = self.client.get(reverse('job_list'), {'location': 'All India'})
        self.assertEqual(resp.status_code, 200)
        jobs = list(resp.context['jobs'])
        self.assertGreaterEqual(len(jobs), 3)

    def test_filter_jobs_multiple_locations(self):
        resp = self.client.get(reverse('job_list'), {'location': 'Bengaluru, Bhubaneswar'})
        self.assertEqual(resp.status_code, 200)
        jobs = list(resp.context['jobs'])
        titles = [j.title for j in jobs]
        self.assertIn("Senior Python Backend Architect", titles)
        self.assertIn("Full Stack Cloud Specialist", titles)
        self.assertNotIn("Lead React Frontend Engineer", titles)


class CandidatePortfolioAndSupabaseStorageTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Candidate A
        self.cand_a_user = User.objects.create_user(
            username="candidate_alice", password="Password123!", role=User.Role.CANDIDATE
        )
        self.cand_a_prof = CandidateProfile.objects.create(
            user=self.cand_a_user, full_name="Alice Candidate", skills="python, django"
        )
        self.resume_a = Resume.objects.create(
            candidate=self.cand_a_user,
            file_name="alice_resume.pdf",
            file_size=2048,
            mime_type="application/pdf",
            extracted_text="Python, Django engineer"
        )

        # Candidate B
        self.cand_b_user = User.objects.create_user(
            username="candidate_bob", password="Password123!", role=User.Role.CANDIDATE
        )
        self.cand_b_prof = CandidateProfile.objects.create(
            user=self.cand_b_user, full_name="Bob Candidate", skills="react"
        )

        # Recruiter
        self.recruiter_user = User.objects.create_user(
            username="recruiter_eva", password="Password123!", role=User.Role.RECRUITER
        )
        self.org = Organization.objects.create(name="Apex Solutions", industry="IT Services")
        OrganizationMember.objects.create(
            organization=self.org, user=self.recruiter_user, role=OrganizationMember.MemberRole.ADMIN
        )
        self.recruiter_prof = RecruiterProfile.objects.create(
            user=self.recruiter_user, company_name="Apex Solutions"
        )
        self.job = Job.objects.create(
            title="Backend Software Engineer",
            organization=self.org,
            recruiter=self.recruiter_user,
            company_name="Apex Solutions",
            location="Bengaluru",
            description="Developing backend architectures.",
            status=Job.Status.ACTIVE
        )

        # Another Recruiter without relationship
        self.unrelated_recruiter = User.objects.create_user(
            username="recruiter_stranger", password="Password123!", role=User.Role.RECRUITER
        )
        RecruiterProfile.objects.create(user=self.unrelated_recruiter, company_name="Other Co")

    def test_file_validation_service(self):
        # 1. Valid PDF
        valid_pdf = SimpleUploadedFile("design_arch.pdf", b"%PDF-1.5 test architecture document", content_type="application/pdf")
        safe_name, mime_type, file_size = SupabaseService.validate_file(valid_pdf)
        self.assertEqual(safe_name, "design_arch.pdf")
        self.assertEqual(mime_type, "application/pdf")
        self.assertGreater(file_size, 0)

        # 2. Valid PNG Image
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        valid_png = SimpleUploadedFile("screenshot.png", png_bytes, content_type="image/png")
        safe_name, mime_type, file_size = SupabaseService.validate_file(valid_png)
        self.assertEqual(safe_name, "screenshot.png")
        self.assertEqual(mime_type, "image/png")

        # 3. Disallowed executable
        bad_exe = SimpleUploadedFile("payload.exe", b"MZ\x90\x00\x03\x00", content_type="application/octet-stream")
        with self.assertRaises(ValidationError) as ctx:
            SupabaseService.validate_file(bad_exe)
        self.assertIn("not permitted", str(ctx.exception))

        # 4. Oversized file (> 50MB)
        huge_file = SimpleUploadedFile("big.zip", b"PK\x03\x04", content_type="application/zip")
        huge_file.size = 55 * 1024 * 1024
        with self.assertRaises(ValidationError) as ctx:
            SupabaseService.validate_file(huge_file)
        self.assertIn("exceeds maximum allowed size", str(ctx.exception))

    @patch.object(SupabaseService, 'upload_file')
    def test_candidate_project_create_with_files(self, mock_upload):
        mock_upload.return_value = True

        self.client.login(username="candidate_alice", password="Password123!")
        pdf_file = SimpleUploadedFile("arch.pdf", b"%PDF-1.4 sample content", content_type="application/pdf")

        post_data = {
            "project_name": "Autonomous Drone Fleet Controller",
            "description": "Distributed real-time fleet coordination platform with fault tolerance.",
            "category": "Web Development",
            "technologies": "Python, Django, Celery, Redis, Docker, PostgreSQL",
            "github_url": "https://github.com/alice/drone-fleet",
            "live_demo_url": "https://drone-fleet.example.com",
            "video_url": "https://youtube.com/watch?v=sample123",
            "project_files": [pdf_file]
        }

        resp = self.client.post(reverse('candidate_project_create'), post_data)
        self.assertEqual(resp.status_code, 302)

        # Verify portfolio in DB
        proj = ProjectPortfolio.objects.filter(candidate=self.cand_a_user, project_name="Autonomous Drone Fleet Controller").first()
        self.assertIsNotNone(proj)
        self.assertEqual(proj.category, "Web Development")
        self.assertIn("Python", proj.technologies)

        # Verify ProjectFile created
        files = proj.files.all()
        self.assertEqual(files.count(), 1)
        pf = files.first()
        self.assertEqual(pf.file_name, "arch.pdf")
        self.assertIn("candidates/", pf.file_path)

    @patch.object(SupabaseService, 'create_signed_url')
    def test_secure_signed_url_download_and_access_control(self, mock_signed_url):
        mock_signed_url.return_value = "https://lnvmixljyhujzkoxlfvw.supabase.co/storage/v1/object/sign/candidate-projects/cand_1/sec.pdf?token=xyz"

        # Create Alice's project & file
        proj = ProjectPortfolio.objects.create(
            candidate=self.cand_a_user,
            project_name="AI Voice Assistant",
            technologies="Python, PyTorch",
        )
        pfile = ProjectFile.objects.create(
            project=proj,
            candidate=self.cand_a_user,
            file_name="secret_design.pdf",
            file_path="candidates/1/projects/1/secret_design.pdf",
            file_type="application/pdf",
            file_size=1024,
        )

        # 1. Unauthenticated user cannot download (redirects to login)
        self.client.logout()
        resp = self.client.get(reverse('candidate_project_file_download', kwargs={'pk': pfile.id}))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

        # 2. Candidate B (unauthorized candidate) gets 403 Forbidden
        self.client.login(username="candidate_bob", password="Password123!")
        resp = self.client.get(reverse('candidate_project_file_download', kwargs={'pk': pfile.id}))
        self.assertEqual(resp.status_code, 403)

        # 3. Unrelated Recruiter gets 403 Forbidden
        self.client.login(username="recruiter_stranger", password="Password123!")
        resp = self.client.get(reverse('candidate_project_file_download', kwargs={'pk': pfile.id}))
        self.assertEqual(resp.status_code, 403)

        # 4. Candidate A (owner) is authorized -> receives HTTP 302 redirect to signed URL
        self.client.login(username="candidate_alice", password="Password123!")
        resp = self.client.get(reverse('candidate_project_file_download', kwargs={'pk': pfile.id}))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("https://lnvmixljyhujzkoxlfvw.supabase.co", resp.url)

        # 5. Employer Recruiter with application relationship
        # Alice applies to Eva's job
        Application.objects.create(
            job=self.job,
            candidate=self.cand_a_user,
            resume=self.resume_a,
            status=Application.Status.APPLIED
        )
        self.client.login(username="recruiter_eva", password="Password123!")
        resp = self.client.get(reverse('candidate_project_file_download', kwargs={'pk': pfile.id}))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("https://lnvmixljyhujzkoxlfvw.supabase.co", resp.url)

    def test_hr_candidate_portfolio_view(self):
        proj = ProjectPortfolio.objects.create(
            candidate=self.cand_a_user,
            project_name="Microservices Architecture",
            description="High throughput event bus",
            technologies="Kafka, Golang, Docker",
            github_url="https://github.com/alice/event-bus"
        )

        # Unrelated recruiter blocked
        self.client.login(username="recruiter_stranger", password="Password123!")
        resp = self.client.get(reverse('hr_candidate_portfolio_view', kwargs={'candidate_id': self.cand_a_prof.id}))
        self.assertEqual(resp.status_code, 403)

        # Recruiter with application allowed
        Application.objects.create(
            job=self.job,
            candidate=self.cand_a_user,
            resume=self.resume_a,
            status=Application.Status.ROUND_1
        )
        self.client.login(username="recruiter_eva", password="Password123!")
        resp = self.client.get(reverse('hr_candidate_portfolio_view', kwargs={'candidate_id': self.cand_a_prof.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Microservices Architecture")
        self.assertContains(resp, "https://github.com/alice/event-bus")

    @patch.object(SupabaseService, 'delete_file')
    def test_project_edit_and_delete(self, mock_delete):
        mock_delete.return_value = True

        self.client.login(username="candidate_alice", password="Password123!")
        proj = ProjectPortfolio.objects.create(
            candidate=self.cand_a_user,
            project_name="Legacy Project",
            description="Old description",
            technologies="PHP, MySQL",
        )
        pfile = ProjectFile.objects.create(
            project=proj,
            candidate=self.cand_a_user,
            file_name="legacy.doc",
            file_path="candidates/1/projects/1/legacy.doc",
            file_type="application/msword",
            file_size=2048,
        )

        # Edit project
        resp = self.client.post(reverse('candidate_project_edit', kwargs={'pk': proj.id}), {
            "project_name": "Upgraded Project",
            "description": "New description",
            "category": "Cloud / DevOps",
            "technologies": "Python, Django, FastAPI",
        })
        self.assertEqual(resp.status_code, 302)
        proj.refresh_from_db()
        self.assertEqual(proj.project_name, "Upgraded Project")

        # Delete individual file
        resp_fdel = self.client.post(reverse('candidate_project_file_delete', kwargs={'pk': pfile.id}))
        self.assertEqual(resp_fdel.status_code, 302)
        self.assertFalse(ProjectFile.objects.filter(id=pfile.id).exists())
        mock_delete.assert_called_with("candidate-projects", "candidates/1/projects/1/legacy.doc")

        # Delete entire project
        resp_pdel = self.client.post(reverse('candidate_project_delete', kwargs={'pk': proj.id}))
        self.assertEqual(resp_pdel.status_code, 302)
        self.assertFalse(ProjectPortfolio.objects.filter(id=proj.id).exists())
