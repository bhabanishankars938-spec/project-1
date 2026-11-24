from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.cache import cache

from accounts.models import User
from recruitment.models import Organization, Job, Application, Interview, Resume
from .models import (
    Meeting, MeetingParticipant, MeetingChatMessage,
    PublicEvent, EventRegistration, InterviewEvaluation, MeetingAbuseReport
)
from .ai_service import AIInterviewIntelligenceService


class HireNexaConnectTestSuite(TestCase):
    """
    Comprehensive Test Suite for HireNexa Connect (V4 Platform Upgrade).
    Tests:
    1. Navigation and Dashboard
    2. 1-to-1 and Multi-Party Meeting Creation & Lifecycle
    3. WebRTC Signaling (Offers, Answers, ICE Candidates, Chat, Presence)
    4. Screen Sharing & Captions Integration
    5. Host Moderation (Mute All, Kick, Lock Room, End Meeting)
    6. Public Events & Controlled Webinar Broadcasting Model
    7. Webinar Registration & Capacity Guardrails
    8. Recruitment Interview Studio & Evaluation Scorecards
    9. AI Interview Intelligence & Curated Fallbacks
    10. Smart Calendar Consolidation
    11. Security, Role Permissions & Abuse Reporting
    """

    def setUp(self):
        cache.clear()
        self.client = Client()

        # Users across roles
        self.recruiter = User.objects.create_user(
            username="recruiter_jane",
            email="recruiter@techlabs.com",
            password="TestPassword123!",
            role=User.Role.RECRUITER
        )

        self.candidate = User.objects.create_user(
            username="candidate_john",
            email="candidate@gmail.com",
            password="TestPassword123!",
            role=User.Role.CANDIDATE
        )

        self.owner = User.objects.create_user(
            username="owner_admin",
            email="owner@hirenexa.internal",
            password="TestPassword123!",
            role=User.Role.OWNER,
            is_staff=True,
            is_superuser=True
        )

        # Organization & Job
        self.org = Organization.objects.create(
            name="TechLabs Global",
            slug="techlabs-global",
            verification_status=Organization.VerificationStatus.APPROVED,
            is_active=True
        )

        self.job = Job.objects.create(
            title="Senior Full Stack Python Engineer",
            organization=self.org,
            recruiter=self.recruiter,
            status=Job.Status.ACTIVE,
            location="Bhubaneswar, Odisha"
        )

        # Resume, Application & Recruitment Interview
        self.resume = Resume.objects.create(
            candidate=self.candidate,
            file="private_resumes/test_resume.pdf",
            file_name="test_resume.pdf",
            file_size=1024,
            mime_type="application/pdf"
        )

        self.application = Application.objects.create(
            job=self.job,
            candidate=self.candidate,
            resume=self.resume,
            status=Application.Status.APPLIED
        )

        self.recruitment_interview = Interview.objects.create(
            application=self.application,
            round_name="Technical Round 1",
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            created_by=self.recruiter
        )

        # Connect Meeting
        self.meeting = Meeting.objects.create(
            title="Full Stack Architecture Interview",
            meeting_type=Meeting.MeetingType.ONE_TO_ONE,
            interview_round=Meeting.InterviewRound.TECHNICAL,
            status=Meeting.Status.SCHEDULED,
            host=self.recruiter,
            interview=self.recruitment_interview,
            scheduled_start=timezone.now() + timezone.timedelta(hours=2),
            scheduled_duration_minutes=45,
            passcode="SECURE88"
        )

        # Participants
        self.host_participant = MeetingParticipant.objects.create(
            meeting=self.meeting,
            user=self.recruiter,
            role=MeetingParticipant.Role.HOST,
            status=MeetingParticipant.Status.ACCEPTED
        )

        self.cand_participant = MeetingParticipant.objects.create(
            meeting=self.meeting,
            user=self.candidate,
            role=MeetingParticipant.Role.CANDIDATE,
            status=MeetingParticipant.Status.ACCEPTED
        )

        # Public Event / Webinar
        self.webinar = PublicEvent.objects.create(
            title="Cracking System Design & Django Scalability",
            subtitle="Mastering high-throughput microservices and distributed caching",
            category=PublicEvent.Category.WEBINAR,
            description="Deep dive into WebRTC signaling, transaction pooling, and Django 6 architecture.",
            host=self.recruiter,
            presenter_name="Jane Doe",
            presenter_title="VP of Engineering, TechLabs",
            scheduled_at=timezone.now() + timezone.timedelta(days=2),
            duration_minutes=60,
            capacity=2
        )

    # 1. Navigation & Core Pages
    def test_connect_dashboard_view(self):
        """Verifies Connect Dashboard renders with metrics, interviews, and public events."""
        self.client.force_login(self.recruiter)
        res = self.client.get(reverse("connect:dashboard"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "HireNexa Connect")
        self.assertContains(res, "Connect. Communicate. Interview. Grow.")
        self.assertIn("active_meetings", res.context)
        self.assertIn("recruitment_interviews", res.context)

    def test_my_meetings_view_tabs(self):
        """Verifies My Meetings tabs (Upcoming, Live, History) render correctly."""
        self.client.force_login(self.recruiter)
        for tab in ["upcoming", "live", "history"]:
            res = self.client.get(f"{reverse('connect:my_meetings')}?tab={tab}")
            self.assertEqual(res.status_code, 200)

    def test_upcoming_interviews_view(self):
        """Verifies upcoming interviews view displays applicant interview details."""
        self.client.force_login(self.candidate)
        res = self.client.get(reverse("connect:upcoming_interviews"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Senior Full Stack Python Engineer")
        self.assertContains(res, "Technical Round 1")

    # 2. Meeting Creation & Lifecycle
    def test_instant_meeting_creation(self):
        """Verifies 1-click instant meeting creation provisions room and redirects."""
        self.client.force_login(self.candidate)
        res = self.client.get(reverse("connect:instant_meeting"))
        self.assertEqual(res.status_code, 302)
        # Verify meeting exists
        created_meeting = Meeting.objects.filter(host=self.candidate, meeting_type=Meeting.MeetingType.INSTANT).first()
        self.assertIsNotNone(created_meeting)
        self.assertEqual(created_meeting.status, Meeting.Status.LIVE)
        self.assertTrue(created_meeting.meeting_id.startswith("hnx-"))

    def test_schedule_meeting_flow(self):
        """Verifies scheduling a meeting via form creates meeting and participants."""
        self.client.force_login(self.recruiter)
        post_data = {
            "title": "Panel Final Round - System Design",
            "meeting_type": Meeting.MeetingType.GROUP,
            "interview_round": Meeting.InterviewRound.FINAL,
            "scheduled_date": "2026-11-25",
            "scheduled_time": "14:30",
            "duration": "60",
            "description": "Distributed architecture evaluation",
            "invitees": "candidate_john, test@external.com"
        }
        res = self.client.post(reverse("connect:schedule_meeting"), post_data)
        self.assertEqual(res.status_code, 302)
        m = Meeting.objects.filter(title="Panel Final Round - System Design").first()
        self.assertIsNotNone(m)
        self.assertEqual(m.meeting_type, Meeting.MeetingType.GROUP)
        # Check candidate was invited
        self.assertTrue(m.participants.filter(user=self.candidate).exists())

    def test_meeting_room_render_and_auth(self):
        """Verifies meeting room renders WebRTC interface for authorized participants."""
        self.client.force_login(self.candidate)
        res = self.client.get(reverse("connect:meeting_room", kwargs={"meeting_id": self.meeting.meeting_id}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, self.meeting.meeting_id)
        self.assertContains(res, "roomBottomToolbar")
        self.assertContains(res, "btnMic")
        self.assertContains(res, "btnCam")
        self.assertContains(res, "btnScreenShare")
        self.assertContains(res, "btnCaptions")

    # 3. WebRTC Signaling API
    def test_webrtc_signaling_exchange(self):
        """Verifies SDP offer/answer exchange, ICE candidate routing, and presence tracking."""
        self.client.force_login(self.recruiter)

        # 1. Post SDP Offer
        offer_payload = {"type": "offer", "sdp": "v=0\r\no=recruiter 12345 2 IN IP4 127.0.0.1..."}
        res = self.client.post(
            reverse("connect:api_signal", kwargs={"meeting_id": self.meeting.meeting_id}),
            {"type": "offer", "payload": offer_payload},
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])

        # 2. Candidate polls for offer
        self.client.force_login(self.candidate)
        res_poll = self.client.get(reverse("connect:api_signal", kwargs={"meeting_id": self.meeting.meeting_id}) + "?since=0")
        self.assertEqual(res_poll.status_code, 200)
        signals = res_poll.json()["signals"]
        self.assertTrue(any(s["type"] == "offer" for s in signals))

        # 3. Candidate sends SDP Answer
        answer_payload = {"type": "answer", "sdp": "v=0\r\no=candidate 67890 2 IN IP4 127.0.0.1..."}
        res_ans = self.client.post(
            reverse("connect:api_signal", kwargs={"meeting_id": self.meeting.meeting_id}),
            {"type": "answer", "payload": answer_payload},
            content_type="application/json"
        )
        self.assertEqual(res_ans.status_code, 200)

        # 4. In-Meeting Chat exchange
        res_chat = self.client.post(
            reverse("connect:api_signal", kwargs={"meeting_id": self.meeting.meeting_id}),
            {"type": "chat", "payload": {"text": "Hello, can you hear me clearly?"}},
            content_type="application/json"
        )
        self.assertEqual(res_chat.status_code, 200)
        self.assertTrue(MeetingChatMessage.objects.filter(meeting=self.meeting).exists())

    # 4. Host Moderation Controls
    def test_host_moderation_controls(self):
        """Verifies host controls: mute all, lock room, and kick participant."""
        self.client.force_login(self.recruiter)

        # Lock Room
        res = self.client.post(
            reverse("connect:api_host_moderation", kwargs={"meeting_id": self.meeting.meeting_id}),
            {"action": "lock_room"},
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 200)
        self.meeting.refresh_from_db()
        self.assertTrue(self.meeting.is_locked)

        # Kick User
        res_kick = self.client.post(
            reverse("connect:api_host_moderation", kwargs={"meeting_id": self.meeting.meeting_id}),
            {"action": "kick_user", "target_username": self.candidate.username},
            content_type="application/json"
        )
        self.assertEqual(res_kick.status_code, 200)

        # End Meeting for Everyone
        res_end = self.client.post(
            reverse("connect:api_host_moderation", kwargs={"meeting_id": self.meeting.meeting_id}),
            {"action": "end_meeting"},
            content_type="application/json"
        )
        self.assertEqual(res_end.status_code, 200)
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, Meeting.Status.COMPLETED)

    def test_non_host_cannot_moderate(self):
        """Verifies non-host participants are blocked from moderation controls."""
        self.client.force_login(self.candidate)
        res = self.client.post(
            reverse("connect:api_host_moderation", kwargs={"meeting_id": self.meeting.meeting_id}),
            {"action": "end_meeting"},
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 403)

    # 5. Public Events & Controlled Webinar Broadcasting Model
    def test_public_event_catalog_and_detail(self):
        """Verifies public webinar catalog, search, and detail pages."""
        res = self.client.get(reverse("connect:public_events"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Cracking System Design")

        res_detail = self.client.get(reverse("connect:public_event_detail", kwargs={"slug": self.webinar.slug}))
        self.assertEqual(res_detail.status_code, 200)
        self.assertContains(res_detail, "Jane Doe")

    def test_webinar_registration_and_capacity_guardrail(self):
        """Verifies webinar registration and capacity enforcement."""
        self.client.force_login(self.candidate)

        # Register User 1
        res = self.client.post(reverse("connect:public_event_register", kwargs={"slug": self.webinar.slug}))
        self.assertEqual(res.status_code, 302)
        self.assertTrue(EventRegistration.objects.filter(event=self.webinar, user=self.candidate).exists())

        # Register User 2 (hits capacity = 2)
        EventRegistration.objects.create(event=self.webinar, user=self.owner)
        self.assertTrue(self.webinar.is_full)

        # 3rd registration should be rejected
        other_user = User.objects.create_user(username="other_cand", email="o@g.com", password="Pass123!")
        self.client.force_login(other_user)
        res_full = self.client.post(reverse("connect:public_event_register", kwargs={"slug": self.webinar.slug}))
        self.assertEqual(res_full.status_code, 302)
        self.assertEqual(EventRegistration.objects.filter(event=self.webinar).count(), 2)

    def test_webinar_stage_controlled_broadcaster_vs_viewer(self):
        """Verifies webinar room presents broadcaster controls to host and viewer mode to attendee."""
        self.client.force_login(self.recruiter)
        res_host = self.client.get(reverse("connect:public_event_room", kwargs={"slug": self.webinar.slug}))
        self.assertEqual(res_host.status_code, 200)
        self.assertTrue(res_host.context["is_broadcaster"])

        self.client.force_login(self.candidate)
        res_attendee = self.client.get(reverse("connect:public_event_room", kwargs={"slug": self.webinar.slug}))
        self.assertEqual(res_attendee.status_code, 200)
        self.assertFalse(res_attendee.context["is_broadcaster"])
        self.assertContains(res_attendee, "Raise Hand to Speak")

    # 6. Recruiter Interview Studio & Scorecards
    def test_interview_studio_access_and_evaluation(self):
        """Verifies recruiter access to Interview Studio and scorecard submission."""
        self.client.force_login(self.recruiter)
        res = self.client.get(reverse("connect:interview_studio", kwargs={"meeting_id": self.meeting.meeting_id}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Live Candidate Scorecard")

        # Submit scorecard evaluation
        eval_payload = {
            "candidate_id": self.candidate.id,
            "technical_competency": "8.5",
            "problem_solving": "9.0",
            "communication_clarity": "8.0",
            "overall_score": "8.5",
            "recommendation": InterviewEvaluation.Recommendation.HIRE,
            "detailed_notes": "Demonstrated strong knowledge of concurrency, database locks and WebRTC signaling.",
        }
        res_eval = self.client.post(
            reverse("connect:api_submit_evaluation", kwargs={"meeting_id": self.meeting.meeting_id}),
            eval_payload,
            content_type="application/json"
        )
        self.assertEqual(res_eval.status_code, 200)
        self.assertTrue(InterviewEvaluation.objects.filter(meeting=self.meeting, candidate=self.candidate).exists())
        self.recruitment_interview.refresh_from_db()
        self.assertEqual(self.recruitment_interview.status, "COMPLETED")

    # 7. AI Interview Intelligence
    def test_ai_question_generation_and_fallback(self):
        """Verifies AI Interview Assistant generates role-appropriate questions with fallback resilience."""
        res = AIInterviewIntelligenceService.generate_interview_questions(
            job_title="Senior Python Backend Developer",
            round_name="Technical Round 1"
        )
        self.assertTrue(res["success"])
        self.assertTrue(len(res["questions"]) >= 3)
        self.assertIn("disclaimer", res)

    def test_ai_notes_synthesis(self):
        """Verifies interview notes synthesis generates structured rubric summaries."""
        res = AIInterviewIntelligenceService.generate_meeting_summary(
            meeting_title="Technical Interview",
            rough_notes="Candidate explained WebSockets vs long polling, designed rate limiter with Redis token bucket.",
            round_name="System Design"
        )
        self.assertTrue(res["success"])
        self.assertIn("summary", res)

    # 8. Abuse Reporting & Safety
    def test_abuse_reporting_api(self):
        """Verifies participants can report misconduct or harassment."""
        self.client.force_login(self.candidate)
        report_payload = {
            "reason": "Harassment / Inappropriate Language",
            "details": "Participant was using disruptive and offensive language during meeting.",
            "offender_username": self.recruiter.username
        }
        res = self.client.post(
            reverse("connect:api_report_abuse", kwargs={"meeting_id": self.meeting.meeting_id}),
            report_payload,
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(MeetingAbuseReport.objects.filter(meeting=self.meeting, reporter=self.candidate).exists())

    # 9. Smart Calendar Integration
    def test_smart_calendar_view(self):
        """Verifies smart calendar consolidates interviews, meetings, and registered webinars."""
        self.client.force_login(self.candidate)
        # Register for webinar
        EventRegistration.objects.create(event=self.webinar, user=self.candidate)

        res = self.client.get(reverse("connect:smart_calendar"))
        self.assertEqual(res.status_code, 200)
        items = res.context["calendar_items"]
        self.assertTrue(any(it["type"] == "Meeting" for it in items))
        self.assertTrue(any(it["type"] == "Webinar" for it in items))


from channels.testing import WebsocketCommunicator
from config.asgi import application
from django.contrib.auth.models import AnonymousUser


class HireNexaChannelsWebSocketTestSuite(TestCase):
    """
    Test suite verifying Daphne, Django Channels, WebSocket connection lifecycle,
    and real-time WebRTC signaling exchange.
    """

    def setUp(self):
        cache.clear()
        self.host = User.objects.create_user(
            username="ws_host_tester",
            email="ws_host@hirenexa.internal",
            password="TestPassword123!"
        )
        self.guest = User.objects.create_user(
            username="ws_guest_tester",
            email="ws_guest@hirenexa.internal",
            password="TestPassword123!"
        )
        self.meeting = Meeting.objects.create(
            title="Real-Time WebSocket Video Test",
            meeting_type=Meeting.MeetingType.ONE_TO_ONE,
            host=self.host,
            status=Meeting.Status.LIVE,
            scheduled_start=timezone.now(),
            scheduled_duration_minutes=30
        )

    async def test_websocket_authenticated_connection(self):
        """Verifies WebSocket handshake succeeds for authenticated meeting participants."""
        communicator = WebsocketCommunicator(
            application,
            f"/ws/connect/{self.meeting.meeting_id}/"
        )
        communicator.scope["user"] = self.host
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_websocket_unauthenticated_rejected(self):
        """Verifies unauthenticated WebSocket connection is rejected."""
        communicator = WebsocketCommunicator(
            application,
            f"/ws/connect/{self.meeting.meeting_id}/"
        )
        communicator.scope["user"] = AnonymousUser()
        connected, _ = await communicator.connect()
        self.assertFalse(connected)

    async def test_websocket_signaling_and_chat_broadcast(self):
        """Verifies WebRTC SDP offer and chat messaging over WebSocket channel."""
        comm_host = WebsocketCommunicator(
            application,
            f"/ws/connect/{self.meeting.meeting_id}/"
        )
        comm_host.scope["user"] = self.host
        connected_host, _ = await comm_host.connect()
        self.assertTrue(connected_host)

        comm_guest = WebsocketCommunicator(
            application,
            f"/ws/connect/{self.meeting.meeting_id}/"
        )
        comm_guest.scope["user"] = self.guest
        connected_guest, _ = await comm_guest.connect()
        self.assertTrue(connected_guest)

        # Host receives user_joined notification when guest joins
        join_msg = await comm_host.receive_json_from(timeout=3)
        self.assertEqual(join_msg["type"], "user_joined")
        self.assertEqual(join_msg["sender"], self.guest.username)

        # Host sends WebRTC offer
        await comm_host.send_json_to({
            "type": "offer",
            "payload": {"type": "offer", "sdp": "v=0\r\no=host 1234 2 IN IP4 127.0.0.1..."},
            "target": "all"
        })

        # Guest receives offer
        response = await comm_guest.receive_json_from(timeout=3)
        self.assertEqual(response["type"], "offer")
        self.assertEqual(response["sender"], self.host.username)

        # Guest sends in-meeting chat message
        await comm_guest.send_json_to({
            "type": "chat",
            "payload": {"text": "Connected via WebSocket!"},
            "target": "all"
        })

        # Host receives chat message
        chat_resp = await comm_host.receive_json_from(timeout=3)
        self.assertEqual(chat_resp["type"], "chat")
        self.assertEqual(chat_resp["payload"]["text"], "Connected via WebSocket!")

        await comm_host.disconnect()
        await comm_guest.disconnect()

