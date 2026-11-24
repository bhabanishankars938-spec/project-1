import io
import json
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image

from recruitment.models import Application, Job, Organization, Resume
from .ai_service import AIService
from .file_processor import FileProcessorService
from .models import AIConversation, AIMessage, AIMessageAttachment
from .prompts import build_system_prompt
from .tools import HireNexaToolRegistry
from .web_research import WebResearchService

User = get_user_model()


class AIAssistantTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Create Platform Owner
        self.owner = User.objects.create_superuser(
            username="test_admin",
            email="admin@hirenexa.com",
            password="Password@123",
            role=User.Role.OWNER,
        )

        # Create Candidate
        self.candidate = User.objects.create_user(
            username="rahul_candidate",
            email="rahul@example.com",
            password="Password@123",
            role=User.Role.CANDIDATE,
        )

        # Create Recruiter
        self.recruiter = User.objects.create_user(
            username="sarah_recruiter",
            email="sarah@techcorp.com",
            password="Password@123",
            role=User.Role.RECRUITER,
        )

        # Create Organization
        self.org = Organization.objects.create(
            name="TechCorp India",
            industry="Software & AI",
            location="Bhubaneswar",
            verification_status=Organization.VerificationStatus.APPROVED,
        )

        # Create Job
        self.job = Job.objects.create(
            organization=self.org,
            recruiter=self.recruiter,
            title="Senior Python / Django Developer",
            company_name="TechCorp India",
            location="Bhubaneswar",
            required_skills="Python, Django, PostgreSQL, Docker, REST API",
            vacancies=5,
            status=Job.Status.ACTIVE,
            is_active=True,
        )

        # Create Resume for candidate
        self.resume = Resume.objects.create(
            candidate=self.candidate,
            file_name="rahul_resume.pdf",
            extracted_text="Python, Django, SQL, Git, REST API experience. MCA graduate.",
        )

        # Create Application
        self.app = Application.objects.create(
            candidate=self.candidate,
            job=self.job,
            resume=self.resume,
            status=Application.Status.ROUND_1,
        )

    # 1. UI View Tests
    def test_ai_assistant_view(self):
        response = self.client.get(reverse("ai_assistant"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "HireNexa AI")
        self.assertContains(response, "Ask Anything. Solve Problems. Build Your Future.")

    # 2. Conversation CRUD API Tests
    def test_conversation_create_and_list(self):
        self.client.force_login(self.candidate)
        create_resp = self.client.post(
            reverse("ai_conversation_create"),
            data=json.dumps({"title": "Python Debugging Help", "mode": "CODING", "language": "en"}),
            content_type="application/json",
        )
        self.assertEqual(create_resp.status_code, 200)
        data = create_resp.json()
        self.assertTrue(data["success"])
        conv_uuid = data["conversation"]["uuid"]

        # List conversations
        list_resp = self.client.get(reverse("ai_conversation_list"))
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(len(list_resp.json()["conversations"]), 1)

        # Rename conversation
        rename_resp = self.client.post(
            reverse("ai_conversation_rename", kwargs={"conv_uuid": conv_uuid}),
            data=json.dumps({"title": "Updated Python Topic"}),
            content_type="application/json",
        )
        self.assertEqual(rename_resp.status_code, 200)
        self.assertEqual(rename_resp.json()["title"], "Updated Python Topic")

        # Delete conversation
        del_resp = self.client.post(reverse("ai_conversation_delete", kwargs={"conv_uuid": conv_uuid}))
        self.assertEqual(del_resp.status_code, 200)
        self.assertEqual(AIConversation.objects.count(), 0)

    # 3. Tool Execution: Search Jobs
    def test_tool_search_jobs(self):
        res = HireNexaToolRegistry.execute_tool("search_jobs", {"query": "Python", "location": "Bhubaneswar"}, user=self.candidate)
        self.assertTrue(res["success"])
        self.assertGreaterEqual(res["count"], 1)
        self.assertEqual(res["results"][0]["title"], "Senior Python / Django Developer")

    # 4. Tool Execution: Search Companies
    def test_tool_search_companies(self):
        res = HireNexaToolRegistry.execute_tool("search_companies", {"query": "TechCorp"}, user=self.candidate)
        self.assertTrue(res["success"])
        self.assertGreaterEqual(res["count"], 1)
        self.assertEqual(res["results"][0]["name"], "TechCorp India")

    # 5. Tool Execution: Platform Stats
    def test_tool_platform_stats(self):
        res = HireNexaToolRegistry.execute_tool("get_platform_stats", {}, user=None)
        self.assertTrue(res["success"])
        self.assertGreaterEqual(res["active_vacancies_count"], 1)

    # 6. Candidate Tool: Get My Applications
    def test_tool_candidate_applications_authorized(self):
        res = HireNexaToolRegistry.execute_tool("get_my_applications", {}, user=self.candidate)
        self.assertTrue(res["success"])
        self.assertEqual(res["total_applications"], 1)
        self.assertEqual(res["applications"][0]["job_title"], "Senior Python / Django Developer")

    def test_tool_candidate_applications_unauthorized_guest(self):
        res = HireNexaToolRegistry.execute_tool("get_my_applications", {}, user=None)
        self.assertFalse(res["success"])
        self.assertIn("Authentication required", res["error"])

    # 7. Candidate Tool: Analyze Resume
    def test_tool_analyze_resume(self):
        res = HireNexaToolRegistry.execute_tool("analyze_candidate_resume", {"target_role_or_job_id": "Python"}, user=self.candidate)
        self.assertTrue(res["success"])
        self.assertTrue(res["has_uploaded_resume"])
        self.assertGreaterEqual(res["overall_match_percentage"], 50)

    # 8. Recruiter Tool: Get My Posted Jobs
    def test_tool_recruiter_posted_jobs_authorized(self):
        res = HireNexaToolRegistry.execute_tool("get_my_posted_jobs", {}, user=self.recruiter)
        self.assertTrue(res["success"])
        self.assertEqual(res["jobs_count"], 1)
        self.assertEqual(res["jobs"][0]["total_applicants"], 1)

    def test_tool_recruiter_posted_jobs_denied_to_candidate(self):
        res = HireNexaToolRegistry.execute_tool("get_my_posted_jobs", {}, user=self.candidate)
        self.assertFalse(res["success"])
        self.assertIn("exclusively available for HR Recruiters", res["error"])

    # 9. Multilingual Prompts
    def test_multilingual_system_prompts(self):
        prompt_en = build_system_prompt(user=self.candidate, mode="CODING", language="en")
        self.assertIn("HireNexa AI", prompt_en)
        self.assertIn("Advanced Coding", prompt_en)

        prompt_hi = build_system_prompt(user=self.candidate, mode="CAREER", language="hi")
        self.assertIn("हिंदी", prompt_hi)

        prompt_or = build_system_prompt(user=self.candidate, mode="GENERAL", language="or")
        self.assertIn("ଓଡ଼ିଆ", prompt_or)

    # 10. File Validation & Multimodal Processing
    def test_file_processor_image_validation(self):
        # Create a valid in-memory image
        img = Image.new("RGB", (100, 100), color="blue")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        uploaded = SimpleUploadedFile("screenshot.png", img_bytes.read(), content_type="image/png")
        is_valid, ftype, err = FileProcessorService.validate_file(uploaded)
        self.assertTrue(is_valid)
        self.assertEqual(ftype, "image")

        proc = FileProcessorService.process_image_attachment(uploaded)
        self.assertEqual(proc["mime_type"], "image/png")
        self.assertTrue(len(proc["base64_data"]) > 0)

    # 11. Text Extraction
    def test_file_processor_text_extraction(self):
        text_content = "This is a sample document text containing software engineering requirements."
        uploaded_doc = SimpleUploadedFile("notes.txt", text_content.encode("utf-8"), content_type="text/plain")
        extracted = FileProcessorService.extract_document_text(uploaded_doc)
        self.assertEqual(extracted, text_content)

    # 12. File Upload API
    def test_file_upload_api(self):
        doc = SimpleUploadedFile("notes.txt", b"System design principles for scalable APIs.", content_type="text/plain")
        resp = self.client.post(reverse("ai_file_upload"), {"file": doc})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["attachment"]["file_name"], "notes.txt")

    # 13. Feedback API
    def test_message_feedback_api(self):
        conv = AIConversation.objects.create(user=self.candidate, title="Feedback Test")
        msg = AIMessage.objects.create(conversation=conv, role=AIMessage.Role.ASSISTANT, content="Test response")
        resp = self.client.post(
            reverse("ai_message_feedback", kwargs={"message_id": msg.id}),
            data=json.dumps({"feedback": "like"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        msg.refresh_from_db()
        self.assertEqual(msg.feedback, AIMessage.Feedback.LIKE)

    # 14. Status API
    def test_ai_status_api(self):
        resp = self.client.get(reverse("ai_status_api"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("search_jobs", data["tools"])

    # 15. Streaming SSE endpoint (Missing key guidance zero-fake test)
    def test_chat_stream_missing_key_guidance(self):
        self.client.force_login(self.candidate)
        conv = AIConversation.objects.create(user=self.candidate, title="Streaming Test")
        resp = self.client.post(
            reverse("ai_chat_stream", kwargs={"conv_uuid": conv.uuid}),
            data=json.dumps({"message": "Find Python developer jobs in Bhubaneswar"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/event-stream")

        # Read streamed content
        content = b"".join(resp.streaming_content).decode("utf-8")
        self.assertIn("tool", content)
        self.assertIn("search_jobs", content)
        self.assertIn("Senior Python / Django Developer", content)

    # 16. Hybrid Provider: OpenAI Success Stream
    def test_hybrid_openai_stream_success(self):
        from unittest.mock import patch, MagicMock
        self.client.force_login(self.candidate)
        conv = AIConversation.objects.create(user=self.candidate, title="OpenAI Success")

        # Mock OpenAI streaming response
        def mock_stream(*args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.iter_lines.return_value = [
                'data: {"choices": [{"delta": {"content": "async/await is "}}]}',
                'data: {"choices": [{"delta": {"content": "syntactic sugar for Promises."}}]}',
                'data: [DONE]'
            ]
            cm = MagicMock()
            cm.__enter__.return_value = mock_resp
            return cm

        with patch("os.environ.get", side_effect=lambda k, d="": "sk-test-valid-key" if k == "OPENAI_API_KEY" else d):
            with patch("httpx.Client.stream", side_effect=mock_stream):
                resp = self.client.post(
                    reverse("ai_chat_stream", kwargs={"conv_uuid": conv.uuid}),
                    data=json.dumps({"message": "Explain async/await in JavaScript"}),
                    content_type="application/json",
                )
                self.assertEqual(resp.status_code, 200)
                content = b"".join(resp.streaming_content).decode("utf-8")
                self.assertIn("async/await is ", content)
                self.assertIn("syntactic sugar for Promises.", content)
                self.assertIn("openai", content.lower())

    # 17. Hybrid Provider: OpenAI 401 Authentication Error (Ineligible for Fallback)
    def test_hybrid_openai_401_ineligible_fallback(self):
        from unittest.mock import patch, MagicMock
        self.client.force_login(self.candidate)
        conv = AIConversation.objects.create(user=self.candidate, title="OpenAI 401")

        def mock_stream(*args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_resp.read.return_value = b'{"error": {"message": "Incorrect API key provided"}}'
            cm = MagicMock()
            cm.__enter__.return_value = mock_resp
            return cm

        with patch("os.environ.get", side_effect=lambda k, d="": "sk-invalid-key" if k == "OPENAI_API_KEY" else d):
            with patch("httpx.Client.stream", side_effect=mock_stream):
                resp = self.client.post(
                    reverse("ai_chat_stream", kwargs={"conv_uuid": conv.uuid}),
                    data=json.dumps({"message": "Write a Python program to reverse a string."}),
                    content_type="application/json",
                )
                self.assertEqual(resp.status_code, 200)
                content = b"".join(resp.streaming_content).decode("utf-8")
                # Must report Authentication error, must NOT fallback to Ollama
                self.assertIn("Authentication Failed", content)
                self.assertNotIn("ollama", content.lower())

    # 18. Hybrid Provider: OpenAI 429 Rate Limit Triggers Eligible Fallback to Ollama
    def test_hybrid_openai_429_eligible_fallback_to_ollama(self):
        from unittest.mock import patch, MagicMock
        self.client.force_login(self.candidate)
        conv = AIConversation.objects.create(user=self.candidate, title="OpenAI Fallback Test")

        # First call (OpenAI) returns 429; second call (Ollama) returns 200
        def mock_stream(*args, **kwargs):
            mock_resp = MagicMock()
            # Find URL in positional args or kwargs
            all_str = " ".join([str(a) for a in args]) + " " + " ".join([f"{k}:{v}" for k, v in kwargs.items()])
            if "openai.com" in all_str:
                mock_resp.status_code = 429
                mock_resp.read.return_value = b'{"error": {"message": "Rate limit reached"}}'
            else:
                # Ollama endpoint
                mock_resp.status_code = 200
                mock_resp.iter_lines.return_value = [
                    '{"message": {"content": "DBMS Normalization is the process of organizing data to reduce redundancy."}}'
                ]
            cm = MagicMock()
            cm.__enter__.return_value = mock_resp
            return cm

        with patch("os.environ.get", side_effect=lambda k, d="": "sk-valid-key" if k == "OPENAI_API_KEY" else d):
            with patch("ai_assistant.ai_service.OllamaProvider.is_available", return_value=(True, "Ollama online")):
                with patch("httpx.Client.stream", side_effect=mock_stream):
                    resp = self.client.post(
                        reverse("ai_chat_stream", kwargs={"conv_uuid": conv.uuid}),
                        data=json.dumps({"message": "Explain DBMS normalization."}),
                        content_type="application/json",
                    )
                    self.assertEqual(resp.status_code, 200)
                    content = b"".join(resp.streaming_content).decode("utf-8")
                    # Verify fallback event was emitted and Ollama content was streamed
                    self.assertIn("provider_fallback", content)
                    self.assertIn("DBMS Normalization", content)

    # 19. Task 3 Prompts Verification
    def test_prompts_and_modes(self):
        # Coding mode prompt
        coding_prompt = build_system_prompt(user=self.candidate, mode="CODING", language="en")
        self.assertIn("Advanced Coding & Technical", coding_prompt)

        # Career mode prompt
        career_prompt = build_system_prompt(user=self.candidate, mode="CAREER", language="en")
        self.assertIn("Career & Recruitment", career_prompt)

        # Docs & Vision mode prompt
        docs_prompt = build_system_prompt(user=self.candidate, mode="DOCS", language="en")
        self.assertIn("Document & Image Analysis", docs_prompt)

        # Language selection tests
        hi_prompt = build_system_prompt(user=self.candidate, mode="GENERAL", language="hi")
        self.assertIn("हिंदी", hi_prompt)

        or_prompt = build_system_prompt(user=self.candidate, mode="GENERAL", language="or")
        self.assertIn("ଓଡ଼ିଆ", or_prompt)

        hinglish_prompt = build_system_prompt(user=self.candidate, mode="GENERAL", language="hinglish")
        self.assertIn("Hinglish", hinglish_prompt)

    # 20. Google AI Studio (Gemini) Provider Streaming
    def test_gemini_provider_streaming(self):
        from unittest.mock import patch, MagicMock
        self.client.force_login(self.candidate)
        conv = AIConversation.objects.create(user=self.candidate, title="Gemini Stream Test")

        def mock_stream(*args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.iter_lines.return_value = [
                'data: {"candidates": [{"content": {"parts": [{"text": "Python program to reverse a string:\\n\\n```python\\ntext = \\"HireNexa\\"\\nreversed_text = text[::-1]\\nprint(reversed_text)\\n```"}]}}]}'
            ]
            cm = MagicMock()
            cm.__enter__.return_value = mock_resp
            return cm

        # No OpenAI key, but Gemini key present
        def env_mock(k, d=""):
            if k == "OPENAI_API_KEY":
                return ""
            if k == "GEMINI_API_KEY":
                return "AIzaSyTestGeminiKeyFromAIStudio"
            return d

        with patch("os.environ.get", side_effect=env_mock):
            with patch("httpx.Client.stream", side_effect=mock_stream):
                resp = self.client.post(
                    reverse("ai_chat_stream", kwargs={"conv_uuid": conv.uuid}),
                    data=json.dumps({"message": "Write a Python program to reverse a string."}),
                    content_type="application/json",
                )
                self.assertEqual(resp.status_code, 200)
                content = b"".join(resp.streaming_content).decode("utf-8")
                self.assertIn("gemini", content.lower())
                self.assertIn("reversed_text", content)

    # 21. Tool Execution: Freelance Projects
    def test_tool_search_freelance_projects(self):
        from recruitment.models import Project
        project = Project.objects.create(
            client=self.owner,
            title="Django & React SaaS Platform",
            description="Need full-stack engineer to build REST APIs and interactive dashboards.",
            required_skills="Django, React, PostgreSQL",
            budget_type=Project.BudgetType.FIXED,
            budget_min=45000,
            budget_max=60000,
            is_active=True,
        )
        res = HireNexaToolRegistry.execute_tool("search_freelance_projects", {"query": "Django"}, user=self.candidate)
        self.assertTrue(res["success"])
        self.assertGreaterEqual(res["count"], 1)
        self.assertIn("Django & React SaaS Platform", [p["title"] for p in res["results"]])

    # 22. Tool Execution: MCA Prep Info
    def test_tool_get_mca_prep_info(self):
        res = HireNexaToolRegistry.execute_tool("get_mca_prep_info", {"target_exam_or_topic": "OJEE"}, user=self.candidate)
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "get_mca_prep_info")
        self.assertTrue(len(res["active_entrance_exams"]) > 0)
        self.assertEqual(res["prep_hub_url"], "/assessments/entrance-prep/")

    # 23. Tool Execution: Search Candidates (Authorized for Recruiter, Denied for Guest)
    def test_tool_search_candidates_rbac(self):
        from recruitment.models import CandidateProfile
        CandidateProfile.objects.update_or_create(
            user=self.candidate,
            defaults={
                "full_name": "Rahul Verma",
                "headline": "Full-Stack Python Engineer",
                "skills": "Python, Django, PostgreSQL, React",
                "education": "Master of Computer Applications (MCA)",
                "university": "Utkal University",
            }
        )
        # Recruiter authorized
        res_recruiter = HireNexaToolRegistry.execute_tool("search_candidates", {"skill": "Python"}, user=self.recruiter)
        self.assertTrue(res_recruiter["success"])
        self.assertGreaterEqual(res_recruiter["count"], 1)

        # Candidate denied
        res_candidate = HireNexaToolRegistry.execute_tool("search_candidates", {"skill": "Python"}, user=self.candidate)
        self.assertFalse(res_candidate["success"])
        self.assertIn("restricted to HR Recruiters", res_candidate["error"])

    # 24. Tool Execution: Admin Governance Summary (Owner authorized, Candidate denied)
    def test_tool_admin_governance_summary_rbac(self):
        # Owner authorized
        res_owner = HireNexaToolRegistry.execute_tool("get_admin_governance_summary", {}, user=self.owner)
        self.assertTrue(res_owner["success"])
        self.assertGreaterEqual(res_owner["active_vacancies_count"], 1)
        self.assertEqual(res_owner["owner_dashboard_url"], "/owner/")

        # Candidate denied
        res_candidate = HireNexaToolRegistry.execute_tool("get_admin_governance_summary", {}, user=self.candidate)
        self.assertFalse(res_candidate["success"])
        self.assertIn("restricted to Platform Owners", res_candidate["error"])

    # 25. Groq Provider Streaming
    def test_groq_provider_streaming(self):
        from unittest.mock import patch, MagicMock
        self.client.force_login(self.candidate)
        conv = AIConversation.objects.create(user=self.candidate, title="Groq Stream Test")

        def mock_stream(*args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.iter_lines.return_value = [
                'data: {"choices": [{"delta": {"content": "Fast inference with Groq."}}]}',
                'data: [DONE]'
            ]
            cm = MagicMock()
            cm.__enter__.return_value = mock_resp
            return cm

        def env_mock(k, d=""):
            if k == "OPENAI_API_KEY":
                return ""
            if k == "GEMINI_API_KEY":
                return ""
            if k == "GROQ_API_KEY":
                return "gsk_test_groq_valid_key"
            return d

        with patch("os.environ.get", side_effect=env_mock):
            with patch("httpx.Client.stream", side_effect=mock_stream):
                resp = self.client.post(
                    reverse("ai_chat_stream", kwargs={"conv_uuid": conv.uuid}),
                    data=json.dumps({"message": "Hello from Groq"}),
                    content_type="application/json",
                )
                self.assertEqual(resp.status_code, 200)
                content = b"".join(resp.streaming_content).decode("utf-8")
                self.assertIn("Groq", content)
                self.assertIn("Fast inference with Groq.", content)

    # 26. Local Platform Intelligence Provider Streaming (Fallback when no keys)
    def test_local_platform_intelligence_fallback_stream(self):
        self.client.force_login(self.candidate)
        conv = AIConversation.objects.create(user=self.candidate, title="Local Platform Test")

        def env_mock(k, d=""):
            if k in ["OPENAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "ANTHROPIC_API_KEY"]:
                return ""
            return d

        from unittest.mock import patch
        with patch("os.environ.get", side_effect=env_mock):
            resp = self.client.post(
                reverse("ai_chat_stream", kwargs={"conv_uuid": conv.uuid}),
                data=json.dumps({"message": "Find Python developer jobs in Bhubaneswar"}),
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 200)
            content = b"".join(resp.streaming_content).decode("utf-8")
            self.assertIn("search_jobs", content)
            self.assertIn("Senior Python / Django Developer", content)
            self.assertIn("HireNexa Platform Intelligence", content)


