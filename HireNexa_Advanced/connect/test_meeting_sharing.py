import json
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from connect.models import Meeting, MeetingParticipant, MeetingInvitation


class LiveMeetingSharingSystemTest(TestCase):
    """
    Comprehensive test suite verifying HireNexa V4 Live Meeting Sharing System:
    1. Create Instant & Scheduled Meetings with unique codes (hnx-xxx-xxx)
    2. Start Meeting transition (SCHEDULED -> LIVE)
    3. Join Meeting via direct link, code, and passcode verification
    4. Multi-platform sharing URL generation (WhatsApp, Email, Telegram, Direct Link)
    5. Sending & recording meeting invitations (MeetingInvitation model)
    6. Waiting room enforcement & host approval / denial flow
    7. Participant status polling API
    8. Host moderation & role permissions
    """

    def setUp(self):
        self.client = Client()
        
        # Create Host User
        self.host = User.objects.create_user(
            username="host_recruiter",
            email="host@hirenexa.internal",
            password="StrongPassword123!",
            role=User.Role.RECRUITER,
            first_name="Jane",
            last_name="Host"
        )
        
        # Create Attendee User
        self.attendee = User.objects.create_user(
            username="candidate_attendee",
            email="attendee@hirenexa.internal",
            password="StrongPassword123!",
            role=User.Role.CANDIDATE,
            first_name="Alex",
            last_name="Candidate"
        )

        # Create External User
        self.external_user = User.objects.create_user(
            username="guest_user",
            email="guest@external.com",
            password="StrongPassword123!",
            role=User.Role.CANDIDATE,
            first_name="Bob",
            last_name="Guest"
        )

    def test_01_instant_meeting_creation(self):
        """Verify 1-click instant meeting generation with unique room code."""
        self.client.force_login(self.host)
        response = self.client.get(reverse("connect:instant_meeting"))
        self.assertEqual(response.status_code, 302)
        
        meeting = Meeting.objects.filter(host=self.host, meeting_type=Meeting.MeetingType.INSTANT).first()
        self.assertIsNotNone(meeting)
        self.assertTrue(meeting.meeting_id.startswith("hnx-"))
        self.assertEqual(meeting.status, Meeting.Status.LIVE)
        
        # Host is automatically registered as HOST and IN_MEETING
        host_part = MeetingParticipant.objects.filter(meeting=meeting, user=self.host).first()
        self.assertIsNotNone(host_part)
        self.assertEqual(host_part.role, MeetingParticipant.Role.HOST)
        self.assertEqual(host_part.status, MeetingParticipant.Status.IN_MEETING)

    def test_02_scheduled_meeting_creation_and_start(self):
        """Verify scheduling a meeting and transitioning from SCHEDULED to LIVE."""
        self.client.force_login(self.host)
        
        # Schedule meeting
        meeting = Meeting.objects.create(
            title="Senior Backend Engineering Interview",
            host=self.host,
            meeting_type=Meeting.MeetingType.ONE_TO_ONE,
            status=Meeting.Status.SCHEDULED,
            scheduled_start=timezone.now() + timezone.timedelta(hours=2),
            scheduled_duration_minutes=60,
            passcode="SECURE88",
            waiting_room_enabled=True
        )
        self.assertEqual(meeting.status, Meeting.Status.SCHEDULED)
        self.assertTrue(meeting.meeting_id.startswith("hnx-"))

        # Non-host cannot start meeting
        self.client.force_login(self.attendee)
        res_fail = self.client.get(reverse("connect:start_meeting", kwargs={"meeting_id": meeting.meeting_id}))
        self.assertEqual(res_fail.status_code, 302)
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, Meeting.Status.SCHEDULED)

        # Host starts meeting
        self.client.force_login(self.host)
        res_start = self.client.get(reverse("connect:start_meeting", kwargs={"meeting_id": meeting.meeting_id}))
        self.assertEqual(res_start.status_code, 302)
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, Meeting.Status.LIVE)
        self.assertIsNotNone(meeting.actual_start)

    def test_03_join_meeting_flow_and_passcode_validation(self):
        """Verify join portal validates codes, handles full URLs, and checks passcodes."""
        meeting = Meeting.objects.create(
            title="Design Review Sync",
            host=self.host,
            status=Meeting.Status.LIVE,
            passcode="PASS123",
            waiting_room_enabled=False
        )
        
        self.client.force_login(self.attendee)
        
        # 1. Invalid room code
        res_bad = self.client.post(reverse("connect:join_meeting"), {"meeting_id": "non-existent-code"})
        self.assertEqual(res_bad.status_code, 200)
        self.assertContains(res_bad, "No meeting found with room code")

        # 2. Correct code but missing / incorrect passcode
        res_wrong_pass = self.client.post(reverse("connect:join_meeting"), {
            "meeting_id": meeting.meeting_id,
            "passcode": "WRONG"
        })
        self.assertEqual(res_wrong_pass.status_code, 200)
        self.assertContains(res_wrong_pass, "Invalid meeting passcode")

        # 3. Correct code and correct passcode -> Redirects to meeting room
        res_success = self.client.post(reverse("connect:join_meeting"), {
            "meeting_id": meeting.meeting_id,
            "passcode": "PASS123"
        })
        self.assertEqual(res_success.status_code, 302)
        self.assertIn(meeting.meeting_id, res_success.url)

        # 4. Pasting a full URL e.g. "https://hirenexa.internal/connect/room/hnx-xxx-xxx/"
        full_url_input = f"https://hirenexa.internal/connect/room/{meeting.meeting_id}/"
        res_url = self.client.post(reverse("connect:join_meeting"), {
            "meeting_id": full_url_input,
            "passcode": "PASS123"
        })
        self.assertEqual(res_url.status_code, 302)
        self.assertIn(meeting.meeting_id, res_url.url)

    def test_04_share_info_api_and_platform_links(self):
        """Verify the share info API generates valid WhatsApp, Telegram, Email, and direct URLs."""
        meeting = Meeting.objects.create(
            title="Product Strategy Sync",
            host=self.host,
            status=Meeting.Status.LIVE,
            passcode="STRAT99"
        )
        
        res = self.client.get(reverse("connect:meeting_share_info", kwargs={"meeting_id": meeting.meeting_id}))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        
        self.assertTrue(data["success"])
        self.assertEqual(data["meeting_id"], meeting.meeting_id)
        self.assertEqual(data["title"], "Product Strategy Sync")
        self.assertIn("whatsapp.com", data["whatsapp_url"])
        self.assertIn("mailto:", data["email_url"])
        self.assertIn("t.me", data["telegram_url"])
        self.assertIn(meeting.meeting_id, data["share_url"])

    def test_05_send_meeting_invitation_api(self):
        """Verify host can send invitations, recording MeetingInvitation and notifying participants."""
        meeting = Meeting.objects.create(
            title="Executive Leadership Panel",
            host=self.host,
            status=Meeting.Status.SCHEDULED
        )
        
        self.client.force_login(self.host)
        
        # Send invitation to an existing platform user
        payload = {
            "recipient": "guest_user",
            "role": MeetingParticipant.Role.ATTENDEE
        }
        res = self.client.post(
            reverse("connect:api_send_invitation", kwargs={"meeting_id": meeting.meeting_id}),
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        
        # Verify MeetingInvitation DB record
        invite = MeetingInvitation.objects.filter(meeting=meeting, invitee_user=self.external_user).first()
        self.assertIsNotNone(invite)
        self.assertEqual(invite.status, MeetingInvitation.Status.PENDING)
        self.assertEqual(invite.invited_by, self.host)

        # Non-host cannot send invitations
        self.client.force_login(self.attendee)
        res_denied = self.client.post(
            reverse("connect:api_send_invitation", kwargs={"meeting_id": meeting.meeting_id}),
            data=json.dumps({"recipient": "someone@test.com"}),
            content_type="application/json"
        )
        self.assertEqual(res_denied.status_code, 403)

    def test_06_waiting_room_and_host_approval_flow(self):
        """
        Verify complete waiting room lifecycle:
        1. Non-host enters room with waiting_room_enabled -> status is WAITING_ROOM.
        2. Attendee sees waiting room screen and polls check_waiting_status_api.
        3. Host receives attendee in waiting room and calls admit_participant_api.
        4. Attendee status changes to IN_MEETING and enters live room.
        """
        meeting = Meeting.objects.create(
            title="Confidential Interview Round",
            host=self.host,
            status=Meeting.Status.LIVE,
            waiting_room_enabled=True
        )

        # 1. Attendee joins meeting room
        self.client.force_login(self.attendee)
        res_room = self.client.get(reverse("connect:meeting_room", kwargs={"meeting_id": meeting.meeting_id}))
        self.assertEqual(res_room.status_code, 200)
        self.assertTrue(res_room.context["in_waiting_room"])
        
        part = MeetingParticipant.objects.filter(meeting=meeting, user=self.attendee).first()
        self.assertIsNotNone(part)
        self.assertEqual(part.status, MeetingParticipant.Status.WAITING_ROOM)

        # 2. Attendee polls waiting status
        res_poll = self.client.get(reverse("connect:api_waiting_status", kwargs={"meeting_id": meeting.meeting_id}))
        self.assertEqual(res_poll.status_code, 200)
        poll_data = res_poll.json()
        self.assertFalse(poll_data["is_admitted"])
        self.assertEqual(poll_data["status"], MeetingParticipant.Status.WAITING_ROOM)

        # 3. Host admits the waiting attendee
        self.client.force_login(self.host)
        res_admit = self.client.post(
            reverse("connect:api_admit_participant", kwargs={"meeting_id": meeting.meeting_id}),
            data=json.dumps({"action": "admit", "participant_id": part.id}),
            content_type="application/json"
        )
        self.assertEqual(res_admit.status_code, 200)
        self.assertTrue(res_admit.json()["success"])
        
        part.refresh_from_db()
        self.assertEqual(part.status, MeetingParticipant.Status.IN_MEETING)

        # 4. Attendee polls again -> is_admitted is now True
        self.client.force_login(self.attendee)
        res_poll2 = self.client.get(reverse("connect:api_waiting_status", kwargs={"meeting_id": meeting.meeting_id}))
        self.assertEqual(res_poll2.status_code, 200)
        self.assertTrue(res_poll2.json()["is_admitted"])

        # 5. Attendee loads meeting room again -> in_waiting_room is now False (Live Room!)
        res_live = self.client.get(reverse("connect:meeting_room", kwargs={"meeting_id": meeting.meeting_id}))
        self.assertEqual(res_live.status_code, 200)
        self.assertFalse(res_live.context["in_waiting_room"])

    def test_07_host_deny_participant_flow(self):
        """Verify host can deny a waiting participant, blocking entry."""
        meeting = Meeting.objects.create(
            title="Private Board Sync",
            host=self.host,
            status=Meeting.Status.LIVE,
            waiting_room_enabled=True
        )

        # Attendee enters waiting room
        self.client.force_login(self.external_user)
        self.client.get(reverse("connect:meeting_room", kwargs={"meeting_id": meeting.meeting_id}))
        part = MeetingParticipant.objects.get(meeting=meeting, user=self.external_user)
        self.assertEqual(part.status, MeetingParticipant.Status.WAITING_ROOM)

        # Host denies participant
        self.client.force_login(self.host)
        res_deny = self.client.post(
            reverse("connect:api_admit_participant", kwargs={"meeting_id": meeting.meeting_id}),
            data=json.dumps({"action": "deny", "participant_id": part.id}),
            content_type="application/json"
        )
        self.assertEqual(res_deny.status_code, 200)
        part.refresh_from_db()
        self.assertEqual(part.status, MeetingParticipant.Status.REMOVED)

        # Attendee checks waiting status -> is_removed is True
        self.client.force_login(self.external_user)
        res_poll = self.client.get(reverse("connect:api_waiting_status", kwargs={"meeting_id": meeting.meeting_id}))
        self.assertTrue(res_poll.json()["is_removed"])

    def test_08_zoom_integration_manual_and_configuration_required(self):
        """
        Verify Zoom integration requirements:
        1. When Zoom credentials are not set, provider returns CONFIGURATION_REQUIRED (no fake URLs).
        2. When recruiter supplies an external Zoom link, it is parsed and preserved.
        3. Zoom meetings generate valid share text and join URLs.
        """
        from recruitment.models import Interview, Application, Job, Organization, Resume
        from recruitment.video_interview_service import ZoomMeetingProvider

        org = Organization.objects.create(name="TechCorp India", slug="techcorp-india")
        job = Job.objects.create(title="Lead Architect", organization=org, recruiter=self.host)
        resume = Resume.objects.create(candidate=self.attendee, file="resumes/dummy.pdf", file_name="dummy.pdf")
        app = Application.objects.create(job=job, candidate=self.attendee, resume=resume)
        interview = Interview.objects.create(
            application=app,
            round_name="System Design",
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            provider=Interview.Provider.ZOOM
        )

        z_prov = ZoomMeetingProvider()
        # Case A: Credentials not configured -> CONFIGURATION_REQUIRED (no fake links!)
        if not z_prov.is_configured:
            info = z_prov.create_meeting(interview)
            self.assertEqual(info["metadata"]["status"], "CONFIGURATION_REQUIRED")
            self.assertEqual(info["join_url"], "")
            self.assertFalse(info["metadata"]["is_configured"])

        # Case B: Recruiter supplies an external Zoom URL manually
        interview.meeting_link = "https://us05web.zoom.us/j/98765432101?pwd=SecretPasscode88"
        interview.save()
        info_manual = z_prov.create_meeting(interview)
        self.assertEqual(info_manual["metadata"]["status"], "CONFIRMED")
        self.assertEqual(info_manual["metadata"]["source"], "MANUAL_LINK")
        self.assertEqual(info_manual["meeting_id"], "98765432101")
        self.assertEqual(info_manual["password"], "SecretPasscode88")
        self.assertIn("us05web.zoom.us", info_manual["join_url"])

        # Case C: Connect Meeting with Zoom provider
        zoom_meeting = Meeting.objects.create(
            title="External Executive Interview",
            host=self.host,
            settings_json={
                "provider": "ZOOM",
                "zoom_join_url": "https://us05web.zoom.us/j/98765432101?pwd=SecretPasscode88"
            }
        )
        self.assertTrue(zoom_meeting.is_zoom)
        self.assertEqual(zoom_meeting.get_join_url(), "https://us05web.zoom.us/j/98765432101?pwd=SecretPasscode88")
        self.assertIn("Zoom Meeting", zoom_meeting.get_share_text())

    def test_09_authentication_multi_identifier_login(self):
        """Verify authentication works across username and email."""
        from accounts.services.auth_service import AuthService

        # 1. Login by Username
        res_user = AuthService.authenticate_portal(None, "host_recruiter", "StrongPassword123!", portal="unified")
        self.assertEqual(res_user["status"], "SUCCESS")
        self.assertEqual(res_user["user"], self.host)

        # 2. Login by Email
        res_email = AuthService.authenticate_portal(None, "host@hirenexa.internal", "StrongPassword123!", portal="unified")
        self.assertEqual(res_email["status"], "SUCCESS")
        self.assertEqual(res_email["user"], self.host)

        # 3. Incorrect Password -> INVALID_CREDENTIALS
        res_fail = AuthService.authenticate_portal(None, "host@hirenexa.internal", "WrongPassword999", portal="unified")
        self.assertEqual(res_fail["status"], "INVALID_CREDENTIALS")

    def test_10_role_based_dashboard_redirects(self):
        """Verify get_role_dashboard_url routes each role to their dedicated workspace."""
        from accounts.views import get_role_dashboard_url

        # Recruiter
        self.assertEqual(get_role_dashboard_url(self.host), reverse("hr_dashboard"))
        # Candidate
        self.assertEqual(get_role_dashboard_url(self.attendee), reverse("candidate_dashboard"))
        # Superuser / Owner
        self.host.is_superuser = True
        self.assertEqual(get_role_dashboard_url(self.host), reverse("owner_dashboard"))
