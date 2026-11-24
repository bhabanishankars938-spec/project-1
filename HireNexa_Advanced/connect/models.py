import uuid
import secrets
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from django.urls import reverse


def generate_meeting_code():
    """Generates a Zoom/Google Meet style human-readable code: hnx-xxx-xxx"""
    chars = "abcdefghjkmnpqrstuvwxyz23456789"
    part1 = "".join(secrets.choice(chars) for _ in range(3))
    part2 = "".join(secrets.choice(chars) for _ in range(3))
    return f"hnx-{part1}-{part2}"


class Meeting(models.Model):
    """
    Central meeting entity powering One-to-One Interviews, Multi-Party Panels,
    Instant Meetings, and Group Team Collaborations.
    """
    class MeetingType(models.TextChoices):
        ONE_TO_ONE = "ONE_TO_ONE", "One-to-One Interview"
        GROUP = "GROUP", "Group Meeting / Panel"
        INSTANT = "INSTANT", "Instant Quick Meeting"
        WEBINAR = "WEBINAR", "Moderated Webinar / Public Event"

    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        WAITING = "WAITING", "Waiting Room Active"
        LIVE = "LIVE", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    class InterviewRound(models.TextChoices):
        TECHNICAL = "TECHNICAL", "Technical Round"
        HR = "HR", "HR Round"
        MANAGER = "MANAGER", "Hiring Manager Round"
        FINAL = "FINAL", "Final Interview"
        GROUP_DISCUSSION = "GROUP_DISCUSSION", "Group Discussion (GD)"
        GENERAL = "GENERAL", "General Meeting / Discussion"

    meeting_id = models.CharField(
        max_length=64,
        unique=True,
        default=generate_meeting_code,
        db_index=True,
        help_text="Secure room code, e.g. hnx-abc-xyz"
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    meeting_type = models.CharField(
        max_length=30,
        choices=MeetingType.choices,
        default=MeetingType.ONE_TO_ONE
    )
    interview_round = models.CharField(
        max_length=30,
        choices=InterviewRound.choices,
        default=InterviewRound.GENERAL
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED,
        db_index=True
    )
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hosted_meetings"
    )
    interview = models.ForeignKey(
        "recruitment.Interview",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connect_meetings",
        help_text="Associated job applicant interview if scheduled via recruitment"
    )
    scheduled_start = models.DateTimeField(default=timezone.now, db_index=True)
    scheduled_duration_minutes = models.PositiveIntegerField(
        default=45,
        help_text="Planned duration in minutes"
    )
    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end = models.DateTimeField(null=True, blank=True)
    passcode = models.CharField(
        max_length=32,
        blank=True,
        help_text="Optional room entry passcode"
    )
    is_locked = models.BooleanField(
        default=False,
        help_text="Host can lock room to prevent new entries"
    )
    waiting_room_enabled = models.BooleanField(
        default=True,
        help_text="Require host approval before participants can enter"
    )
    is_recorded = models.BooleanField(
        default=False,
        help_text="Explicit recording consent state"
    )
    max_participants = models.PositiveIntegerField(default=50)
    settings_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Room config: mute_on_entry, screen_share_allowed, chat_enabled, etc."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scheduled_start"]
        indexes = [
            models.Index(fields=["meeting_id"]),
            models.Index(fields=["status", "scheduled_start"]),
            models.Index(fields=["host", "status"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.meeting_id}) - {self.get_status_display()}"

    def get_absolute_url(self):
        return reverse("connect:meeting_room", kwargs={"meeting_id": self.meeting_id})

    @property
    def is_zoom(self):
        return bool(self.settings_json.get("provider") == "ZOOM" or "zoom.us" in (self.settings_json.get("external_url") or ""))

    def get_join_url(self, request=None):
        external_url = self.settings_json.get("external_url") or self.settings_json.get("zoom_join_url")
        if external_url:
            return external_url
        path = reverse("connect:meeting_room", kwargs={"meeting_id": self.meeting_id})
        if request:
            return request.build_absolute_uri(path)
        return path

    def get_share_text(self, request=None):
        url = self.get_join_url(request)
        provider_name = "Zoom" if self.is_zoom else "HireNexa Live"
        start_str = self.scheduled_start.strftime("%A, %b %d, %Y at %I:%M %p")
        text = (
            f"You're invited to a {provider_name} Meeting!\n\n"
            f"📌 Title: {self.title}\n"
            f"📅 Date & Time: {start_str}\n"
            f"🔑 Meeting ID: {self.meeting_id}\n"
        )
        if self.passcode:
            text += f"🔒 Passcode: {self.passcode}\n"
        text += f"\n🔗 Join Link: {url}\n"
        if not self.is_zoom:
            text += "\nJoin directly in your browser — zero installation required."
        return text

    @property
    def is_active(self):
        return self.status in [self.Status.SCHEDULED, self.Status.WAITING, self.Status.LIVE]

    @property
    def duration_display(self):
        if self.actual_start and self.actual_end:
            secs = int((self.actual_end - self.actual_start).total_seconds())
            mins = secs // 60
            return f"{mins} mins"
        return f"{self.scheduled_duration_minutes} mins"


class MeetingParticipant(models.Model):
    """
    Tracks participants in a meeting: host, co-host, interviewer, candidate, guest.
    Enforces authorization, mute/video states, and attendance tracking.
    """
    class Role(models.TextChoices):
        HOST = "HOST", "Host / Organizer"
        CO_HOST = "CO_HOST", "Co-Host"
        INTERVIEWER = "INTERVIEWER", "Interviewer / Panelist"
        CANDIDATE = "CANDIDATE", "Candidate"
        ATTENDEE = "ATTENDEE", "Attendee / Participant"
        SPEAKER = "SPEAKER", "Featured Presenter"

    class Status(models.TextChoices):
        INVITED = "INVITED", "Invited"
        ACCEPTED = "ACCEPTED", "Accepted Invitation"
        DECLINED = "DECLINED", "Declined Invitation"
        RESCHEDULE_REQUESTED = "RESCHEDULE_REQUESTED", "Requested Reschedule"
        WAITING_ROOM = "WAITING_ROOM", "In Waiting Room"
        IN_MEETING = "IN_MEETING", "Currently In Meeting"
        LEFT = "LEFT", "Left Meeting"
        REMOVED = "REMOVED", "Removed by Host"

    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="participants"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="connect_participations"
    )
    guest_name = models.CharField(max_length=150, blank=True)
    guest_email = models.EmailField(blank=True)
    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        default=Role.ATTENDEE
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.INVITED
    )
    reschedule_preferred_time = models.DateTimeField(null=True, blank=True)
    reschedule_reason = models.TextField(blank=True)
    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    audio_muted = models.BooleanField(default=False)
    video_muted = models.BooleanField(default=False)
    hand_raised = models.BooleanField(default=False)
    can_share_screen = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["role", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["meeting", "user"],
                condition=models.Q(user__isnull=False),
                name="unique_user_meeting_participant"
            )
        ]

    def __str__(self):
        name = self.display_name
        return f"{name} ({self.get_role_display()}) in {self.meeting.meeting_id}"

    @property
    def display_name(self):
        if self.user:
            return self.user.get_full_name() or self.user.username
        return self.guest_name or "Guest"


class MeetingInvitation(models.Model):
    """
    Formal invitation record for tracking email, WhatsApp, and link invites.
    Preserves delivery status, recipient information, and acceptance timestamps.
    """
    class Platform(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        WHATSAPP = "WHATSAPP", "WhatsApp"
        LINK = "LINK", "Direct Link"
        INTERNAL = "INTERNAL", "HireNexa Platform"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted / Joined"
        DECLINED = "DECLINED", "Declined"

    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="invitations"
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_meeting_invitations"
    )
    invitee_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_meeting_invitations"
    )
    recipient_email = models.EmailField(blank=True)
    recipient_phone = models.CharField(max_length=30, blank=True)
    invitation_code = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe)
    platform = models.CharField(max_length=20, choices=Platform.choices, default=Platform.LINK)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    sent_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        target = self.invitee_user.username if self.invitee_user else (self.recipient_email or self.recipient_phone or "Invite")
        return f"Invitation to {target} for {self.meeting.meeting_id} ({self.get_platform_display()})"


class MeetingChatMessage(models.Model):
    """
    In-meeting real-time chat message record.
    Preserves audit history and moderation actions.
    """
    class MessageType(models.TextChoices):
        CHAT = "CHAT", "Public Chat"
        DIRECT = "DIRECT", "Direct Message"
        SYSTEM = "SYSTEM", "System Notice"
        ANNOUNCEMENT = "ANNOUNCEMENT", "Host Announcement"
        QA = "QA", "Q&A Question"

    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="messages"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    sender_name = models.CharField(max_length=150)
    sender_role = models.CharField(max_length=50, blank=True)
    message_type = models.CharField(
        max_length=20,
        choices=MessageType.choices,
        default=MessageType.CHAT
    )
    content = models.TextField()
    is_approved = models.BooleanField(default=True, help_text="Moderation flag for moderated Q&A")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.created_at.strftime('%H:%M:%S')}] {self.sender_name}: {self.content[:30]}"


class PublicEvent(models.Model):
    """
    Moderated public career webinars, recruitment drives, campus placement
    orientations, and developer workshops.
    Uses the controlled webinar broadcast model (attendees are viewers by default).
    """
    class Category(models.TextChoices):
        WEBINAR = "WEBINAR", "Career Guidance Webinar"
        RECRUITMENT_DRIVE = "RECRUITMENT_DRIVE", "Company Recruitment Drive"
        CAMPUS_PLACEMENT = "CAMPUS_PLACEMENT", "Campus Placement Orientation"
        TECHNICAL_WORKSHOP = "TECHNICAL_WORKSHOP", "Developer & Tech Workshop"
        RESUME_CLINIC = "RESUME_CLINIC", "Resume Review & ATS Improvement"
        INTERVIEW_PREP = "INTERVIEW_PREP", "Interview Preparation & Masterclass"

    class Status(models.TextChoices):
        UPCOMING = "UPCOMING", "Upcoming"
        LIVE = "LIVE", "Currently Broadcasting"
        CONCLUDED = "CONCLUDED", "Concluded"
        CANCELLED = "CANCELLED", "Cancelled"

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    subtitle = models.CharField(max_length=350, blank=True)
    category = models.CharField(
        max_length=40,
        choices=Category.choices,
        default=Category.WEBINAR
    )
    description = models.TextField()
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hosted_public_events"
    )
    presenter_name = models.CharField(max_length=150, default="HireNexa Expert")
    presenter_title = models.CharField(max_length=200, default="Industry Leader")
    presenter_bio = models.TextField(blank=True)
    scheduled_at = models.DateTimeField(db_index=True)
    duration_minutes = models.PositiveIntegerField(default=60)
    capacity = models.PositiveIntegerField(default=500)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UPCOMING,
        db_index=True
    )
    is_published = models.BooleanField(default=True)
    meeting = models.OneToOneField(
        Meeting,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="public_event_linked"
    )
    cover_tag = models.CharField(max_length=60, default="Live Interactive Webinar")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scheduled_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title) or "career-event"
            self.slug = f"{base}-{secrets.token_hex(3)}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"

    def get_absolute_url(self):
        return reverse("connect:public_event_detail", kwargs={"slug": self.slug})

    @property
    def registered_count(self):
        return self.registrations.count()

    @property
    def seats_left(self):
        return max(0, self.capacity - self.registered_count)

    @property
    def is_full(self):
        return self.registered_count >= self.capacity


class EventRegistration(models.Model):
    """
    Candidate registration for a moderated public event or webinar.
    """
    event = models.ForeignKey(
        PublicEvent,
        on_delete=models.CASCADE,
        related_name="registrations"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="event_registrations"
    )
    registered_at = models.DateTimeField(auto_now_add=True)
    attended = models.BooleanField(default=False)
    feedback_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    feedback_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-registered_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user"],
                name="unique_user_event_registration"
            )
        ]

    def __str__(self):
        return f"{self.user.username} registered for {self.event.title}"


class InterviewEvaluation(models.Model):
    """
    Structured scorecard and skill evaluation completed by the interviewer
    after or during an interview round. Explainable & human-reviewed.
    """
    class Recommendation(models.TextChoices):
        STRONG_HIRE = "STRONG_HIRE", "Strong Hire"
        HIRE = "HIRE", "Hire (Proceed to Next Round)"
        HOLD = "HOLD", "Hold / Re-evaluate"
        NO_HIRE = "NO_HIRE", "No Hire (Do Not Proceed)"

    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="evaluations"
    )
    interview = models.ForeignKey(
        "recruitment.Interview",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connect_evaluations"
    )
    evaluator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="evaluations_given"
    )
    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="evaluations_received"
    )
    technical_competency = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal("0.0"))
    problem_solving = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal("0.0"))
    communication_clarity = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal("0.0"))
    culture_and_values = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal("0.0"))
    overall_score = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal("0.0"))
    recommendation = models.CharField(
        max_length=30,
        choices=Recommendation.choices,
        default=Recommendation.HIRE
    )
    detailed_notes = models.TextField(blank=True)
    strengths_observed = models.TextField(blank=True)
    areas_for_growth = models.TextField(blank=True)
    ai_generated_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Evaluation for {self.candidate.username} by {self.evaluator.username} ({self.get_recommendation_display()})"


class MeetingAbuseReport(models.Model):
    """
    Abuse reporting entity allowing any participant to report harassment,
    disruption, or misconduct during a video meeting or public webinar.
    """
    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="abuse_reports"
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="abuse_reports_filed"
    )
    offender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="abuse_reports_against"
    )
    reason = models.CharField(max_length=150)
    details = models.TextField()
    is_reviewed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Report in {self.meeting.meeting_id} by {self.reporter.username}"
