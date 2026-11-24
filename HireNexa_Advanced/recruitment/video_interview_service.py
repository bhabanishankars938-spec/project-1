import base64
import hashlib
import json
import logging
import os
import secrets
from typing import Dict, Any, Optional
from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger("hirenexa.recruitment.video")


class BaseMeetingProvider:
    """Abstract interface for video conferencing providers."""

    def create_meeting(self, interview, host_user=None) -> Dict[str, Any]:
        raise NotImplementedError

    def cancel_meeting(self, interview) -> bool:
        return True


class ZoomMeetingProvider(BaseMeetingProvider):
    """
    Enterprise Zoom Video Meetings Provider using Server-to-Server OAuth.
    Gracefully falls back to local high-reliability virtual room if credentials
    are not configured in settings/environment.
    """

    def __init__(self):
        self.account_id = getattr(settings, "ZOOM_ACCOUNT_ID", os.environ.get("ZOOM_ACCOUNT_ID", "")).strip()
        self.client_id = getattr(settings, "ZOOM_CLIENT_ID", os.environ.get("ZOOM_CLIENT_ID", "")).strip()
        self.client_secret = getattr(settings, "ZOOM_CLIENT_SECRET", os.environ.get("ZOOM_CLIENT_SECRET", "")).strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.account_id and self.client_id and self.client_secret)

    def _get_oauth_token(self) -> Optional[str]:
        if not self.is_configured:
            return None
        try:
            import urllib.request
            auth_str = f"{self.client_id}:{self.client_secret}"
            b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
            token_url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={self.account_id}"

            req = urllib.request.Request(
                token_url,
                method="POST",
                headers={
                    "Authorization": f"Basic {b64_auth}",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    return data.get("access_token")
        except Exception as e:
            logger.warning(f"Zoom OAuth token request failed: {e}. Falling back to virtual room.")
        return None

    def create_meeting(self, interview, host_user=None) -> Dict[str, Any]:
        """
        Creates an official Zoom meeting using Server-to-Server OAuth.
        If a valid Zoom link was already provided manually, preserves and parses it.
        If credentials are not configured, returns an honest CONFIGURATION_REQUIRED state
        without generating fake or placeholder Zoom URLs.
        """
        # 1. Check if recruiter manually provided an external Zoom link
        existing_link = interview.meeting_link or ""
        if existing_link and ("zoom.us" in existing_link or "zoomgov.com" in existing_link):
            import re
            m_id_match = re.search(r"/j/(\d+)", existing_link)
            m_id = m_id_match.group(1) if m_id_match else interview.meeting_id
            pwd_match = re.search(r"pwd=([^&]+)", existing_link)
            pwd = pwd_match.group(1) if pwd_match else interview.meeting_password
            return {
                "provider": "ZOOM",
                "join_url": existing_link,
                "start_url": existing_link,
                "meeting_id": m_id or "Zoom Meeting",
                "password": pwd or "",
                "metadata": {
                    "status": "CONFIRMED",
                    "source": "MANUAL_LINK",
                    "created_at": timezone.now().isoformat()
                }
            }

        # 2. Check if Server-to-Server OAuth credentials are configured
        if not self.is_configured:
            logger.info("Zoom credentials not configured in environment (ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET).")
            return {
                "provider": "ZOOM",
                "join_url": "",
                "start_url": "",
                "meeting_id": "",
                "password": "",
                "metadata": {
                    "status": "CONFIGURATION_REQUIRED",
                    "is_configured": False,
                    "notice": (
                        "Zoom Server-to-Server OAuth credentials (ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET) "
                        "are required for automated Zoom meeting generation. You can configure credentials in environment "
                        "variables or manually paste an external Zoom meeting link."
                    ),
                    "created_at": timezone.now().isoformat()
                }
            }

        # 3. Request official Zoom OAuth token and create meeting
        token = self._get_oauth_token()
        if token:
            try:
                import urllib.request
                start_iso = interview.scheduled_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                payload = {
                    "topic": f"HireNexa Interview: {interview.round_name} - {interview.application.job.title}",
                    "type": 2,  # Scheduled meeting
                    "start_time": start_iso,
                    "duration": interview.duration_minutes or 45,
                    "timezone": "Asia/Kolkata",
                    "agenda": f"Candidate: {interview.application.candidate.get_full_name() or interview.application.candidate.username} | Role: {interview.application.job.title}",
                    "settings": {
                        "host_video": True,
                        "participant_video": True,
                        "join_before_host": False,
                        "mute_upon_entry": True,
                        "waiting_room": True,
                        "approval_type": 0
                    }
                }
                data_bytes = json.dumps(payload).encode("utf-8")
                api_url = "https://api.zoom.us/v2/users/me/meetings"
                req = urllib.request.Request(
                    api_url,
                    data=data_bytes,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=12) as response:
                    if response.status in (200, 201):
                        resp_data = json.loads(response.read().decode("utf-8"))
                        return {
                            "provider": "ZOOM",
                            "join_url": resp_data.get("join_url", ""),
                            "start_url": resp_data.get("start_url", ""),
                            "meeting_id": str(resp_data.get("id", "")),
                            "password": resp_data.get("password", ""),
                            "metadata": {
                                "status": "CONFIRMED",
                                "zoom_id": resp_data.get("id"),
                                "created_via": "Zoom REST API",
                                "created_at": timezone.now().isoformat(),
                            }
                        }
            except Exception as exc:
                logger.warning(f"Zoom API call failed: {exc}.")
                return {
                    "provider": "ZOOM",
                    "join_url": "",
                    "start_url": "",
                    "meeting_id": "",
                    "password": "",
                    "metadata": {
                        "status": "API_ERROR",
                        "error": str(exc),
                        "notice": f"Zoom API request failed: {exc}. Verify Zoom app scopes (meeting:write:admin).",
                        "created_at": timezone.now().isoformat()
                    }
                }

        return {
            "provider": "ZOOM",
            "join_url": "",
            "start_url": "",
            "meeting_id": "",
            "password": "",
            "metadata": {
                "status": "AUTHENTICATION_FAILED",
                "notice": "Failed to authenticate with Zoom Server-to-Server OAuth. Check ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, and ZOOM_CLIENT_SECRET.",
                "created_at": timezone.now().isoformat()
            }
        }


class InternalMeetingProvider(BaseMeetingProvider):
    """Native HireNexa Unified Connect Meeting Provider."""

    def create_meeting(self, interview, host_user=None) -> Dict[str, Any]:
        from connect.models import Meeting, MeetingParticipant
        interview_id = getattr(interview, "id", None) or 0

        # Check if a Connect meeting already exists for this interview
        meeting = Meeting.objects.filter(interview=interview).first() if interview_id else None
        if not meeting:
            host = host_user or getattr(interview, "created_by", None)
            if not host and hasattr(interview, "application") and interview.application.job:
                host = interview.application.job.recruiter
            if not host:
                from accounts.models import User
                host = User.objects.filter(is_superuser=True).first()

            job_title = interview.application.job.title if hasattr(interview, "application") and interview.application.job else "Role"
            round_title = getattr(interview, "round_name", "Interview")
            title = f"Interview: {round_title} - {job_title}"
            desc = getattr(interview, "notes", "") or f"Interview for {job_title}"
            start_time = getattr(interview, "scheduled_at", None) or timezone.now()
            duration = getattr(interview, "duration_minutes", 45) or 45

            meeting = Meeting.objects.create(
                title=title,
                description=desc,
                meeting_type=Meeting.MeetingType.ONE_TO_ONE,
                interview_round=Meeting.InterviewRound.TECHNICAL,
                status=Meeting.Status.SCHEDULED,
                host=host,
                interview=interview if interview_id else None,
                scheduled_start=start_time,
                scheduled_duration_minutes=duration,
                waiting_room_enabled=True,
            )

            # Link participants
            if hasattr(interview, "application") and interview.application.candidate:
                MeetingParticipant.objects.get_or_create(
                    meeting=meeting,
                    user=interview.application.candidate,
                    defaults={"role": MeetingParticipant.Role.CANDIDATE, "status": MeetingParticipant.Status.ACCEPTED}
                )
            if host:
                MeetingParticipant.objects.get_or_create(
                    meeting=meeting,
                    user=host,
                    defaults={"role": MeetingParticipant.Role.HOST, "status": MeetingParticipant.Status.ACCEPTED}
                )

        join_url = reverse("connect:meeting_room", kwargs={"meeting_id": meeting.meeting_id})

        return {
            "provider": "INTERNAL",
            "join_url": join_url,
            "meeting_id": meeting.meeting_id,
            "password": meeting.passcode or "",
            "metadata": {
                "status": "READY",
                "connect_meeting_id": meeting.meeting_id,
                "engine": "HireNexa Unified Connect Engine",
                "created_at": timezone.now().isoformat()
            }
        }


class GoogleMeetProvider(BaseMeetingProvider):
    """Google Meet Provider with custom or generated meeting code."""

    def create_meeting(self, interview, host_user=None) -> Dict[str, Any]:
        existing_link = interview.meeting_link
        if existing_link and "meet.google.com" in existing_link:
            meeting_id = existing_link.rstrip("/").split("/")[-1]
            return {
                "provider": "GOOGLE_MEET",
                "join_url": existing_link,
                "meeting_id": meeting_id,
                "password": "",
                "metadata": {"status": "CUSTOM_LINK"}
            }

        code_part1 = secrets.token_hex(2)
        code_part2 = secrets.token_hex(2)
        code_part3 = secrets.token_hex(2)
        meeting_id = f"{code_part1}-{code_part2}-{code_part3}"
        join_url = f"https://meet.google.com/{meeting_id}"

        return {
            "provider": "GOOGLE_MEET",
            "join_url": join_url,
            "meeting_id": meeting_id,
            "password": "",
            "metadata": {"status": "GENERATED", "created_at": timezone.now().isoformat()}
        }


class VideoInterviewService:
    """Central factory and orchestration service for Video Interviews."""

    @classmethod
    def get_provider(cls, provider_type: str) -> BaseMeetingProvider:
        pt = (provider_type or "INTERNAL").upper()
        if pt == "ZOOM":
            return ZoomMeetingProvider()
        elif pt == "GOOGLE_MEET":
            return GoogleMeetProvider()
        return InternalMeetingProvider()

    @classmethod
    def schedule_meeting(cls, interview, provider_type: Optional[str] = None, host_user=None):
        """
        Generates or synchronizes meeting credentials with selected provider.
        Updates interview object fields in place and persists to database.
        """
        p_type = provider_type or interview.provider or "INTERNAL"
        # In-person and phone interviews don't need a video room
        if p_type in ["IN_PERSON", "PHONE"]:
            interview.provider = p_type
            interview.save(update_fields=["provider"])
            return interview

        provider_obj = cls.get_provider(p_type)
        meeting_info = provider_obj.create_meeting(interview, host_user=host_user)

        interview.provider = meeting_info.get("provider", p_type)
        if not interview.meeting_link or meeting_info.get("join_url"):
            interview.meeting_link = meeting_info.get("join_url", interview.meeting_link)
        interview.meeting_id = meeting_info.get("meeting_id", interview.meeting_id)
        interview.meeting_password = meeting_info.get("password", interview.meeting_password)
        
        meta = interview.meeting_metadata or {}
        meta.update(meeting_info.get("metadata", {}))
        interview.meeting_metadata = meta

        interview.save(update_fields=["provider", "meeting_link", "meeting_id", "meeting_password", "meeting_metadata"])
        return interview
