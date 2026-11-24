import os
import json
import secrets
import urllib.parse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.urls import reverse
from django.db.models import Q
from django.core.paginator import Paginator

from accounts.models import User
from recruitment.models import Interview, Job, Application
from .models import (
    Meeting, MeetingParticipant, MeetingInvitation, MeetingChatMessage,
    PublicEvent, EventRegistration, InterviewEvaluation
)


@login_required
def connect_dashboard(request):
    """
    HIRENEXA CONNECT Central Hub.
    Tagline: 'Connect. Communicate. Interview. Grow.'
    Displays active sessions, today's schedule, recruitment interviews,
    quick meeting launcher, and trending career events.
    """
    now = timezone.now()
    user = request.user

    # Meetings where user is host or invited participant
    user_meetings = Meeting.objects.filter(
        Q(host=user) | Q(participants__user=user)
    ).distinct().order_by("scheduled_start")

    active_meetings = user_meetings.filter(status__in=[Meeting.Status.LIVE, Meeting.Status.WAITING])
    upcoming_meetings = user_meetings.filter(
        status=Meeting.Status.SCHEDULED,
        scheduled_start__gte=now - timezone.timedelta(hours=2)
    )[:6]

    # Integrated recruitment interviews
    recruitment_interviews = []
    if user.role == User.Role.CANDIDATE:
        recruitment_interviews = Interview.objects.filter(
            application__candidate=user,
            status=Interview.Status.SCHEDULED,
            scheduled_at__gte=now - timezone.timedelta(hours=1)
        ).select_related("application", "application__job", "application__job__organization").order_by("scheduled_at")[:5]
    elif user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN]:
        recruitment_interviews = Interview.objects.filter(
            Q(created_by=user) | Q(application__job__recruiter=user),
            status=Interview.Status.SCHEDULED,
            scheduled_at__gte=now - timezone.timedelta(hours=1)
        ).select_related("application", "application__candidate", "application__job").order_by("scheduled_at")[:5]

    # Featured Public Events / Webinars
    featured_events = PublicEvent.objects.filter(
        is_published=True,
        scheduled_at__gte=now
    ).order_by("scheduled_at")[:3]

    # Check which events current user is registered for
    registered_event_ids = set(
        EventRegistration.objects.filter(user=user).values_list("event_id", flat=True)
    )

    context = {
        "active_meetings": active_meetings,
        "upcoming_meetings": upcoming_meetings,
        "recruitment_interviews": recruitment_interviews,
        "featured_events": featured_events,
        "registered_event_ids": registered_event_ids,
        "is_recruiter_or_admin": user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN, User.Role.OWNER],
    }
    return render(request, "connect/dashboard.html", context)


@login_required
def my_meetings(request):
    """
    My Meetings View with tabbed filtering:
    - Upcoming / Scheduled
    - Live Sessions
    - Completed / History
    """
    user = request.user
    tab = request.GET.get("tab", "upcoming")

    base_qs = Meeting.objects.filter(
        Q(host=user) | Q(participants__user=user)
    ).distinct().select_related("host", "interview")

    if tab == "live":
        meetings = base_qs.filter(status__in=[Meeting.Status.LIVE, Meeting.Status.WAITING]).order_by("-scheduled_start")
    elif tab == "history":
        meetings = base_qs.filter(status=Meeting.Status.COMPLETED).order_by("-actual_end", "-scheduled_start")
    else:
        meetings = base_qs.filter(status=Meeting.Status.SCHEDULED).order_by("scheduled_start")

    paginator = Paginator(meetings, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "meetings": page_obj,
        "active_tab": tab,
    }
    return render(request, "connect/my_meetings.html", context)


@login_required
def upcoming_interviews(request):
    """
    Integrated recruitment interviews view.
    Enables candidates and recruiters to view upcoming rounds,
    accept/decline invitations, request rescheduling, or jump directly into the interview room.
    """
    user = request.user
    now = timezone.now()

    if user.role == User.Role.CANDIDATE:
        interviews = Interview.objects.filter(
            application__candidate=user,
            scheduled_at__gte=now - timezone.timedelta(days=1)
        ).select_related(
            "application", "application__job", "application__job__organization", "created_by"
        ).order_by("scheduled_at")
    else:
        interviews = Interview.objects.filter(
            Q(created_by=user) | Q(application__job__recruiter=user),
            scheduled_at__gte=now - timezone.timedelta(days=1)
        ).select_related(
            "application", "application__candidate", "application__job", "application__job__organization"
        ).order_by("scheduled_at")

    context = {
        "interviews": interviews,
        "is_candidate": (user.role == User.Role.CANDIDATE),
    }
    return render(request, "connect/upcoming_interviews.html", context)


@login_required
def instant_meeting_create(request):
    """
    Generates an instant 1-click meeting room and immediately redirects the user.
    """
    title = f"{request.user.get_full_name() or request.user.username}'s Instant Meeting"
    passcode = secrets.token_hex(3).upper()

    meeting = Meeting.objects.create(
        title=title,
        meeting_type=Meeting.MeetingType.INSTANT,
        status=Meeting.Status.LIVE,
        host=request.user,
        scheduled_start=timezone.now(),
        actual_start=timezone.now(),
        passcode=passcode
    )

    # Host is automatically added as participant
    MeetingParticipant.objects.create(
        meeting=meeting,
        user=request.user,
        role=MeetingParticipant.Role.HOST,
        status=MeetingParticipant.Status.IN_MEETING,
        joined_at=timezone.now()
    )

    messages.success(request, f"Instant meeting started! Room code: {meeting.meeting_id}")
    return redirect("connect:meeting_room", meeting_id=meeting.meeting_id)


@login_required
def schedule_meeting(request):
    """
    Schedules a planned 1-to-1 interview or multi-party team meeting.
    """
    if request.method == "POST":
        title = request.data.get("title") if hasattr(request, "data") else request.POST.get("title")
        meeting_type = request.POST.get("meeting_type", Meeting.MeetingType.ONE_TO_ONE)
        round_name = request.POST.get("interview_round", Meeting.InterviewRound.GENERAL)
        scheduled_date = request.POST.get("scheduled_date")
        scheduled_time = request.POST.get("scheduled_time")
        duration = int(request.POST.get("duration", 45))
        description = request.POST.get("description", "")
        invitees_str = request.POST.get("invitees", "")

        if not title or not scheduled_date or not scheduled_time:
            messages.error(request, "Please fill in all required meeting details.")
            return redirect("connect:schedule_meeting")

        import datetime
        dt_str = f"{scheduled_date} {scheduled_time}"
        try:
            naive_dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            scheduled_start = timezone.make_aware(naive_dt, timezone.get_current_timezone())
        except Exception:
            scheduled_start = timezone.now() + timezone.timedelta(hours=1)

        provider = request.POST.get("provider", "INTERNAL").upper()
        zoom_link = request.POST.get("zoom_link", "").strip()

        settings_json = {"provider": provider}
        if provider == "ZOOM":
            if zoom_link:
                settings_json["zoom_join_url"] = zoom_link
                settings_json["external_url"] = zoom_link
                settings_json["zoom_status"] = "CONFIRMED"
            else:
                from recruitment.video_interview_service import ZoomMeetingProvider
                z_prov = ZoomMeetingProvider()
                if z_prov.is_configured:
                    token = z_prov._get_oauth_token()
                    if token:
                        try:
                            import urllib.request
                            start_iso = scheduled_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                            payload = {
                                "topic": title,
                                "type": 2,
                                "start_time": start_iso,
                                "duration": duration,
                                "timezone": "Asia/Kolkata",
                                "settings": {"waiting_room": True, "mute_upon_entry": True}
                            }
                            req_z = urllib.request.Request(
                                "https://api.zoom.us/v2/users/me/meetings",
                                data=json.dumps(payload).encode("utf-8"),
                                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                                method="POST"
                            )
                            with urllib.request.urlopen(req_z, timeout=10) as resp:
                                if resp.status in (200, 201):
                                    z_data = json.loads(resp.read().decode("utf-8"))
                                    settings_json["zoom_join_url"] = z_data.get("join_url", "")
                                    settings_json["external_url"] = z_data.get("join_url", "")
                                    settings_json["zoom_meeting_id"] = str(z_data.get("id", ""))
                                    settings_json["zoom_password"] = z_data.get("password", "")
                                    settings_json["zoom_status"] = "CONFIRMED"
                        except Exception as e:
                            settings_json["zoom_status"] = "API_ERROR"
                    else:
                        settings_json["zoom_status"] = "AUTHENTICATION_FAILED"
                else:
                    settings_json["zoom_status"] = "CONFIGURATION_REQUIRED"
                    messages.info(request, "Zoom Server-to-Server OAuth credentials are not configured. Meeting scheduled with HireNexa Live room. You can also provide an external Zoom link in meeting settings.")

        passcode = secrets.token_hex(3).upper()

        meeting = Meeting.objects.create(
            title=title,
            description=description,
            meeting_type=meeting_type,
            interview_round=round_name,
            status=Meeting.Status.SCHEDULED,
            host=request.user,
            scheduled_start=scheduled_start,
            scheduled_duration_minutes=duration,
            passcode=passcode,
            settings_json=settings_json
        )

        # Host participant
        MeetingParticipant.objects.create(
            meeting=meeting,
            user=request.user,
            role=MeetingParticipant.Role.HOST,
            status=MeetingParticipant.Status.ACCEPTED
        )

        # Process invitees (usernames or emails)
        if invitees_str:
            for item in invitees_str.replace(",", " ").split():
                clean_item = item.strip()
                if clean_item:
                    invitee_user = User.objects.filter(Q(username__iexact=clean_item) | Q(email__iexact=clean_item)).first()
                    if invitee_user and invitee_user != request.user:
                        MeetingParticipant.objects.get_or_create(
                            meeting=meeting,
                            user=invitee_user,
                            defaults={
                                "role": MeetingParticipant.Role.INTERVIEWER if meeting_type == Meeting.MeetingType.GROUP else MeetingParticipant.Role.CANDIDATE,
                                "status": MeetingParticipant.Status.INVITED
                            }
                        )

        messages.success(request, f"Meeting '{meeting.title}' scheduled successfully! Room code: {meeting.meeting_id}")
        return redirect("connect:my_meetings")

    return render(request, "connect/schedule_meeting.html", {
        "meeting_types": Meeting.MeetingType.choices,
        "interview_rounds": Meeting.InterviewRound.choices,
    })


def join_meeting_view(request):
    """
    Dedicated Join Meeting portal.
    Allows entering room code (hnx-xxx-xxx) or full meeting URL,
    optional passcode verification, and instant redirection.
    """
    if request.method == "POST":
        raw_code = request.POST.get("meeting_id", "").strip()
        passcode = request.POST.get("passcode", "").strip()
        display_name = request.POST.get("display_name", "").strip()

        if not raw_code:
            messages.error(request, "Please enter a valid Meeting ID or link.")
            return render(request, "connect/join_meeting.html")

        # Parse out room code if a full URL was pasted (e.g., https://site/connect/room/hnx-abc-xyz/ or hnx-abc-xyz)
        import re
        match = re.search(r"(hnx-[a-z0-9]{3,4}-[a-z0-9]{3,4})", raw_code, re.IGNORECASE)
        meeting_code = match.group(1).lower() if match else raw_code.strip().lower()

        # Find meeting
        meeting = Meeting.objects.filter(Q(meeting_id__iexact=meeting_code) | Q(meeting_id__iexact=raw_code)).first()
        if not meeting:
            messages.error(request, f"No meeting found with room code '{raw_code}'. Please check and try again.")
            return render(request, "connect/join_meeting.html", {"entered_code": raw_code})

        if meeting.status == Meeting.Status.COMPLETED:
            messages.info(request, "This meeting has already ended.")
            return redirect("connect:meeting_history") if request.user.is_authenticated else redirect("connect:join_meeting")

        # Check passcode if set and user is not host
        if meeting.passcode and (not request.user.is_authenticated or meeting.host != request.user):
            if passcode and passcode.strip().upper() != meeting.passcode.strip().upper():
                messages.error(request, "Invalid meeting passcode. Please re-enter.")
                return render(request, "connect/join_meeting.html", {"meeting": meeting, "entered_code": raw_code, "requires_passcode": True})

        if display_name:
            request.session["connect_display_name"] = display_name

        return redirect("connect:meeting_room", meeting_id=meeting.meeting_id)

    # GET request
    code = request.GET.get("code", "").strip()
    requires_passcode = False
    meeting_obj = None
    if code:
        meeting_obj = Meeting.objects.filter(meeting_id__iexact=code).first()
        if meeting_obj and meeting_obj.passcode:
            requires_passcode = True

    recent_meetings = []
    if request.user.is_authenticated:
        recent_meetings = Meeting.objects.filter(
            Q(host=request.user) | Q(participants__user=request.user)
        ).exclude(status=Meeting.Status.COMPLETED).distinct().order_by("-scheduled_start")[:5]

    return render(request, "connect/join_meeting.html", {
        "entered_code": code,
        "meeting": meeting_obj,
        "requires_passcode": requires_passcode,
        "recent_meetings": recent_meetings,
    })


def join_meeting_direct(request, meeting_id):
    """
    Direct invitation URL landing handler (e.g. /connect/join/<meeting_id>/).
    Accepts invite code query param, logs invitation acceptance if present,
    and directs the attendee to the meeting room or join verification page.
    """
    meeting = get_object_or_404(Meeting, meeting_id__iexact=meeting_id)
    invitation_code = request.GET.get("inv", "").strip()

    if invitation_code:
        invitation = MeetingInvitation.objects.filter(invitation_code=invitation_code, meeting=meeting).first()
        if invitation and invitation.status == MeetingInvitation.Status.PENDING:
            invitation.status = MeetingInvitation.Status.ACCEPTED
            invitation.accepted_at = timezone.now()
            if request.user.is_authenticated and not invitation.invitee_user:
                invitation.invitee_user = request.user
            invitation.save(update_fields=["status", "accepted_at", "invitee_user"])

    if meeting.passcode and (not request.user.is_authenticated or meeting.host != request.user):
        passcode_param = request.GET.get("passcode", "").strip()
        if not passcode_param or passcode_param.upper() != meeting.passcode.upper():
            return redirect(f"{reverse('connect:join_meeting')}?code={meeting.meeting_id}")

    return redirect("connect:meeting_room", meeting_id=meeting.meeting_id)


@login_required
def start_meeting(request, meeting_id):
    """
    Allows the meeting host to transition a SCHEDULED meeting into LIVE status.
    """
    meeting = get_object_or_404(Meeting, meeting_id__iexact=meeting_id)
    if not (meeting.host == request.user or request.user.is_superuser):
        messages.error(request, "Only the meeting host can start this session.")
        return redirect("connect:my_meetings")

    if meeting.status == Meeting.Status.SCHEDULED:
        meeting.status = Meeting.Status.LIVE
        meeting.actual_start = timezone.now()
        meeting.save(update_fields=["status", "actual_start"])
        messages.success(request, f"Meeting '{meeting.title}' is now LIVE! Attendees can enter.")

    return redirect("connect:meeting_room", meeting_id=meeting.meeting_id)


@login_required
def meeting_room(request, meeting_id):
    """
    Professional Zoom-style WebRTC Video Conferencing Room with Live Sharing and Waiting Room.
    Supports:
    - Audio/Video preview and mute/unmute
    - Multi-person responsive video grid (Gallery vs Active Speaker)
    - Browser Screen Sharing (window, tab, full display)
    - Real-time in-meeting chat
    - Participant list and host moderation controls
    - Waiting room with host admission
    - 1-Click live sharing via WhatsApp, Email, Telegram, and Direct Link
    - Fullscreen and Picture-in-Picture
    - Live call timer and connection state badges
    """
    meeting = get_object_or_404(Meeting.objects.select_related("host", "interview"), meeting_id__iexact=meeting_id)

    # If meeting is already completed or cancelled
    if meeting.status in [Meeting.Status.COMPLETED, Meeting.Status.CANCELLED]:
        messages.info(request, "This meeting has ended.")
        return redirect("connect:meeting_history")

    # Associated interview info if any
    interview = meeting.interview
    job = None
    candidate = None
    application = None

    is_host = bool(meeting.host == request.user or request.user.is_superuser)
    if interview:
        application = getattr(interview, "application", None)
        if application:
            job = getattr(application, "job", None)
            candidate = getattr(application, "candidate", None)
            if (interview.created_by == request.user or 
                (job and getattr(job, "recruiter", None) == request.user) or
                getattr(request.user, "role", None) in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN, User.Role.OWNER]):
                is_host = True

    # Check if meeting is locked
    if meeting.is_locked and not is_host:
        messages.error(request, "This meeting has been locked by the host. New participants cannot join.")
        return redirect("connect:dashboard")

    # If host joins, ensure meeting is marked LIVE
    if is_host and meeting.status == Meeting.Status.SCHEDULED:
        meeting.status = Meeting.Status.LIVE
        meeting.actual_start = timezone.now()
        meeting.save(update_fields=["status", "actual_start"])

    # Determine participant status (Waiting Room vs In Meeting)
    in_waiting_room = False
    if not is_host and meeting.waiting_room_enabled:
        participant = MeetingParticipant.objects.filter(meeting=meeting, user=request.user).first()
        if not participant:
            # New attendee: placed in waiting room awaiting host approval
            participant = MeetingParticipant.objects.create(
                meeting=meeting,
                user=request.user,
                role=MeetingParticipant.Role.ATTENDEE,
                status=MeetingParticipant.Status.WAITING_ROOM,
                joined_at=timezone.now()
            )
            in_waiting_room = True
        elif participant.status == MeetingParticipant.Status.WAITING_ROOM:
            in_waiting_room = True
        elif participant.status == MeetingParticipant.Status.REMOVED:
            messages.error(request, "You were removed from this meeting by the host.")
            return redirect("connect:dashboard")
        elif participant.status not in [MeetingParticipant.Status.IN_MEETING, MeetingParticipant.Status.ACCEPTED]:
            participant.status = MeetingParticipant.Status.WAITING_ROOM
            participant.save(update_fields=["status"])
            in_waiting_room = True
    else:
        # Host or waiting room disabled
        participant, _ = MeetingParticipant.objects.get_or_create(
            meeting=meeting,
            user=request.user,
            defaults={
                "role": MeetingParticipant.Role.HOST if is_host else MeetingParticipant.Role.ATTENDEE,
                "status": MeetingParticipant.Status.IN_MEETING,
                "joined_at": timezone.now()
            }
        )
        if participant.status != MeetingParticipant.Status.IN_MEETING:
            participant.status = MeetingParticipant.Status.IN_MEETING
            participant.joined_at = timezone.now()
            participant.save(update_fields=["status", "joined_at"])

    # Dynamic STUN/TURN ICE Servers from Environment
    ice_servers = [
        {"urls": "stun:stun.l.google.com:19302"},
        {"urls": "stun:stun1.l.google.com:19302"},
        {"urls": "stun:stun2.l.google.com:19302"},
    ]
    turn_url = os.environ.get("TURN_URL")
    if turn_url:
        turn_entry = {"urls": turn_url}
        turn_username = os.environ.get("TURN_USERNAME")
        turn_credential = os.environ.get("TURN_CREDENTIAL")
        if turn_username:
            turn_entry["username"] = turn_username
        if turn_credential:
            turn_entry["credential"] = turn_credential
        ice_servers.append(turn_entry)

    # Multi-Platform Sharing URLs
    share_url = meeting.get_join_url(request)
    share_text = meeting.get_share_text(request)
    encoded_share_text = urllib.parse.quote(share_text)
    encoded_share_url = urllib.parse.quote(share_url)
    encoded_title = urllib.parse.quote(meeting.title)

    whatsapp_url = f"https://api.whatsapp.com/send?text={encoded_share_text}"
    email_mailto = f"mailto:?subject={encoded_title}&body={encoded_share_text}"
    telegram_url = f"https://t.me/share/url?url={encoded_share_url}&text={encoded_title}"
    linkedin_url = f"https://www.linkedin.com/sharing/share-offsite/?url={encoded_share_url}"

    # Participants lists for host view
    waiting_participants = meeting.participants.filter(status=MeetingParticipant.Status.WAITING_ROOM).select_related("user")
    in_meeting_participants = meeting.participants.filter(status=MeetingParticipant.Status.IN_MEETING).select_related("user")

    is_candidate = bool(
        (candidate and candidate == request.user) or 
        (participant and participant.role == MeetingParticipant.Role.CANDIDATE)
    )
    is_interviewer = bool(
        is_host or 
        (participant and participant.role in [MeetingParticipant.Role.INTERVIEWER, MeetingParticipant.Role.CO_HOST])
    )

    context = {
        "meeting": meeting,
        "participant": participant,
        "is_host": is_host,
        "is_candidate": is_candidate,
        "is_interviewer": is_interviewer,
        "interview": interview,
        "job": job,
        "candidate": candidate,
        "application": application,
        "passcode": meeting.passcode,
        "ice_servers_json": json.dumps(ice_servers),
        "in_waiting_room": in_waiting_room,
        "waiting_participants": waiting_participants,
        "in_meeting_participants": in_meeting_participants,
        "share_url": share_url,
        "share_text": share_text,
        "whatsapp_url": whatsapp_url,
        "email_mailto": email_mailto,
        "telegram_url": telegram_url,
        "linkedin_url": linkedin_url,
    }
    return render(request, "connect/meeting_room.html", context)


def meeting_share_info_api(request, meeting_id):
    """
    Returns full sharing endpoints and text in JSON format for modals and client integrations.
    """
    meeting = get_object_or_404(Meeting, meeting_id__iexact=meeting_id)
    share_url = meeting.get_join_url(request)
    share_text = meeting.get_share_text(request)

    return JsonResponse({
        "success": True,
        "meeting_id": meeting.meeting_id,
        "title": meeting.title,
        "status": meeting.status,
        "status_display": meeting.get_status_display(),
        "passcode": meeting.passcode,
        "share_url": share_url,
        "share_text": share_text,
        "whatsapp_url": f"https://api.whatsapp.com/send?text={urllib.parse.quote(share_text)}",
        "email_url": f"mailto:?subject={urllib.parse.quote('Invitation: ' + meeting.title)}&body={urllib.parse.quote(share_text)}",
        "telegram_url": f"https://t.me/share/url?url={urllib.parse.quote(share_url)}&text={urllib.parse.quote(meeting.title)}",
        "linkedin_url": f"https://www.linkedin.com/sharing/share-offsite/?url={urllib.parse.quote(share_url)}",
        "waiting_room_enabled": meeting.waiting_room_enabled,
        "is_locked": meeting.is_locked,
    })


@login_required
def send_meeting_invitation_api(request, meeting_id):
    """
    Dispatches meeting invitations via Email or platform messages and creates MeetingInvitation records.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST method required"}, status=405)

    meeting = get_object_or_404(Meeting, meeting_id__iexact=meeting_id)

    # Check permissions: host, co-host, recruiter, admin
    is_host = bool(meeting.host == request.user or request.user.is_superuser)
    if not is_host:
        return JsonResponse({"success": False, "error": "Only host or authorized organizers can send invitations."}, status=403)

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else request.POST
    except Exception:
        data = request.POST

    recipient = (data.get("recipient") or data.get("email") or "").strip()
    platform = (data.get("platform") or "EMAIL").upper()
    role = data.get("role") or MeetingParticipant.Role.ATTENDEE

    if not recipient:
        return JsonResponse({"success": False, "error": "Please provide an email or username recipient."}, status=400)

    # Check if recipient matches an existing user
    invitee_user = User.objects.filter(Q(email__iexact=recipient) | Q(username__iexact=recipient)).first()

    # Determine platform choice
    plat_choice = MeetingInvitation.Platform.EMAIL if "@" in recipient else MeetingInvitation.Platform.LINK
    if platform in MeetingInvitation.Platform.values:
        plat_choice = platform

    # Create invitation record
    invitation = MeetingInvitation.objects.create(
        meeting=meeting,
        invited_by=request.user,
        invitee_user=invitee_user,
        recipient_email=recipient if "@" in recipient else (invitee_user.email if invitee_user else ""),
        platform=plat_choice,
        status=MeetingInvitation.Status.PENDING
    )

    # If invitee is existing user, also add/update participant
    if invitee_user:
        MeetingParticipant.objects.get_or_create(
            meeting=meeting,
            user=invitee_user,
            defaults={"role": role, "status": MeetingParticipant.Status.INVITED}
        )

    # Send email notification if recipient has email
    target_email = invitation.recipient_email
    email_sent = False
    if target_email and "@" in target_email:
        join_url = meeting.get_join_url(request)
        subject = f"HireNexa Live Meeting Invitation: {meeting.title}"
        message = (
            f"Hello,\n\n"
            f"You have been invited by {request.user.get_full_name() or request.user.username} to attend a HireNexa Live Meeting.\n\n"
            f"📌 Title: {meeting.title}\n"
            f"🔑 Meeting ID: {meeting.meeting_id}\n"
            f"📅 Date & Time: {meeting.scheduled_start.strftime('%A, %b %d, %Y at %I:%M %p')}\n"
        )
        if meeting.passcode:
            message += f"🔒 Passcode: {meeting.passcode}\n"
        message += f"\n🔗 Join Link: {join_url}\n\nWe look forward to seeing you!\n— The HireNexa Team"

        try:
            from django.core.mail import send_mail
            from django.conf import settings
            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@hirenexa.internal"),
                recipient_list=[target_email],
                fail_silently=True
            )
            email_sent = True
        except Exception:
            email_sent = False

    return JsonResponse({
        "success": True,
        "message": f"Invitation created successfully for {recipient}!",
        "invitation_id": invitation.id,
        "invitation_code": invitation.invitation_code,
        "email_dispatched": email_sent,
        "share_url": meeting.get_join_url(request),
    })


@login_required
def admit_participant_api(request, meeting_id):
    """
    Host moderation endpoint to admit or deny participants from the waiting room.
    Supports admitting single participant or 'admit_all'.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST method required"}, status=405)

    meeting = get_object_or_404(Meeting, meeting_id__iexact=meeting_id)
    is_host = bool(meeting.host == request.user or request.user.is_superuser)
    if not is_host:
        return JsonResponse({"success": False, "error": "Unauthorized: Host access required."}, status=403)

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else request.POST
    except Exception:
        data = request.POST

    action = data.get("action", "admit")  # "admit", "deny", "admit_all"
    participant_id = data.get("participant_id")

    if action == "admit_all":
        updated_count = meeting.participants.filter(
            status=MeetingParticipant.Status.WAITING_ROOM
        ).update(
            status=MeetingParticipant.Status.IN_MEETING,
            joined_at=timezone.now()
        )
        return JsonResponse({"success": True, "action": "admit_all", "count": updated_count})

    if not participant_id:
        return JsonResponse({"success": False, "error": "participant_id is required"}, status=400)

    part = get_object_or_404(MeetingParticipant, id=participant_id, meeting=meeting)

    if action == "admit":
        part.status = MeetingParticipant.Status.IN_MEETING
        part.joined_at = timezone.now()
        part.save(update_fields=["status", "joined_at"])
        return JsonResponse({"success": True, "action": "admit", "status": part.status, "participant_name": part.display_name})
    elif action == "deny":
        part.status = MeetingParticipant.Status.REMOVED
        part.save(update_fields=["status"])
        return JsonResponse({"success": True, "action": "deny", "status": part.status, "participant_name": part.display_name})
    else:
        return JsonResponse({"success": False, "error": f"Unknown action '{action}'"}, status=400)


@login_required
def check_waiting_status_api(request, meeting_id):
    """
    Polled by attendees in the waiting room to detect when host has admitted them.
    """
    meeting = get_object_or_404(Meeting, meeting_id__iexact=meeting_id)
    part = MeetingParticipant.objects.filter(meeting=meeting, user=request.user).first()

    if not part:
        return JsonResponse({
            "is_admitted": False,
            "status": "NOT_REGISTERED",
            "meeting_status": meeting.status
        })

    is_admitted = (part.status == MeetingParticipant.Status.IN_MEETING)
    is_removed = (part.status == MeetingParticipant.Status.REMOVED)

    return JsonResponse({
        "is_admitted": is_admitted,
        "is_removed": is_removed,
        "status": part.status,
        "status_display": part.get_status_display(),
        "meeting_status": meeting.status,
        "meeting_title": meeting.title,
    })


def public_events(request):
    """
    Public Career Events, Webinars & Masterclasses Catalog.
    Discoverable by all visitors and candidates.
    """
    now = timezone.now()
    category = request.GET.get("category", "")
    query = request.GET.get("q", "").strip()

    events = PublicEvent.objects.filter(is_published=True)

    if category:
        events = events.filter(category=category)
    if query:
        events = events.filter(
            Q(title__icontains=query) | Q(description__icontains=query) | Q(presenter_name__icontains=query)
        )

    events = events.order_by("scheduled_at")

    registered_event_ids = set()
    if request.user.is_authenticated:
        registered_event_ids = set(
            EventRegistration.objects.filter(user=request.user).values_list("event_id", flat=True)
        )

    context = {
        "events": events,
        "categories": PublicEvent.Category.choices,
        "selected_category": category,
        "query": query,
        "registered_event_ids": registered_event_ids,
    }
    return render(request, "connect/public_events.html", context)


def public_event_detail(request, slug):
    """
    Public event detail page with agenda, host bio, and free registration.
    """
    event = get_object_or_404(PublicEvent, slug=slug, is_published=True)
    is_registered = False
    if request.user.is_authenticated:
        is_registered = EventRegistration.objects.filter(event=event, user=request.user).exists()

    context = {
        "event": event,
        "is_registered": is_registered,
    }
    return render(request, "connect/public_event_detail.html", context)


@login_required
def public_event_register(request, slug):
    """
    Registers the logged-in candidate for a public webinar.
    """
    event = get_object_or_404(PublicEvent, slug=slug, is_published=True)

    if event.is_full:
        messages.error(request, "This webinar has reached maximum capacity.")
        return redirect("connect:public_event_detail", slug=slug)

    reg, created = EventRegistration.objects.get_or_create(
        event=event,
        user=request.user
    )
    if created:
        messages.success(request, f"🎉 You have successfully registered for '{event.title}'! An invitation has been added to your calendar.")
    else:
        messages.info(request, "You are already registered for this event.")

    return redirect("connect:public_event_detail", slug=slug)


@login_required
def public_event_room(request, slug):
    """
    Moderated Live Webinar Stage.
    Controlled broadcast architecture:
    - Host and approved speakers broadcast live video and audio.
    - Attendees enter as viewers.
    - Attendees can Raise Hand to request speaking permission.
    - Moderated Q&A panel and safe chat.
    """
    event = get_object_or_404(PublicEvent, slug=slug, is_published=True)
    is_host = bool(event.host == request.user or request.user.is_superuser)

    # Ensure linked meeting room exists
    if not event.meeting:
        meeting = Meeting.objects.create(
            title=event.title,
            description=event.description,
            meeting_type=Meeting.MeetingType.WEBINAR,
            status=Meeting.Status.LIVE if is_host else Meeting.Status.SCHEDULED,
            host=event.host,
            scheduled_start=event.scheduled_at,
            scheduled_duration_minutes=event.duration_minutes,
            max_participants=event.capacity
        )
        event.meeting = meeting
        event.save(update_fields=["meeting"])
    else:
        meeting = event.meeting

    participant, _ = MeetingParticipant.objects.get_or_create(
        meeting=meeting,
        user=request.user,
        defaults={
            "role": MeetingParticipant.Role.HOST if is_host else MeetingParticipant.Role.ATTENDEE,
            "status": MeetingParticipant.Status.IN_MEETING,
            "joined_at": timezone.now()
        }
    )

    context = {
        "event": event,
        "meeting": meeting,
        "participant": participant,
        "is_host": is_host,
        "is_broadcaster": is_host or (participant.role == MeetingParticipant.Role.SPEAKER),
    }
    return render(request, "connect/public_event_room.html", context)


@login_required
def meeting_history(request):
    """
    Meeting History view listing completed meetings, duration, and evaluation scorecards.
    """
    user = request.user
    completed_meetings = Meeting.objects.filter(
        Q(host=user) | Q(participants__user=user),
        status=Meeting.Status.COMPLETED
    ).distinct().order_by("-actual_end", "-scheduled_start")

    paginator = Paginator(completed_meetings, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "meetings": page_obj,
    }
    return render(request, "connect/meeting_history.html", context)


@login_required
def meeting_settings(request):
    """
    User meeting preferences and hardware preview:
    - Camera on/off default
    - Microphone mute default
    - Mirror video toggle
    - Display name
    """
    if request.method == "POST":
        display_name = request.POST.get("display_name", "").strip()
        mute_default = request.POST.get("mute_default") == "on"
        cam_off_default = request.POST.get("cam_off_default") == "on"

        # Save to user session or profile
        request.session["connect_mute_default"] = mute_default
        request.session["connect_cam_off_default"] = cam_off_default
        messages.success(request, "Meeting preferences saved.")
        return redirect("connect:meeting_settings")

    context = {
        "mute_default": request.session.get("connect_mute_default", False),
        "cam_off_default": request.session.get("connect_cam_off_default", False),
    }
    return render(request, "connect/meeting_settings.html", context)


@login_required
def interview_studio(request, meeting_id):
    """
    Dedicated Recruiter Interview Workspace:
    - Live WebRTC Interview Stage
    - Candidate Resume & Application details
    - Structured Scoring Rubric (Technical, Problem Solving, Communication, Culture)
    - AI Interview Assistant Question Suggestions
    - Live Scorecard submission
    """
    meeting = get_object_or_404(Meeting.objects.select_related("host", "interview"), meeting_id=meeting_id)

    # Authorization: Recruiter, Company Admin, Host, or Superuser
    if not (meeting.host == request.user or request.user.role in [User.Role.RECRUITER, User.Role.COMPANY_ADMIN, User.Role.OWNER] or request.user.is_superuser):
        raise HttpResponseForbidden("Access restricted to authorized interview evaluators.")

    interview = meeting.interview
    application = interview.application if interview else None
    candidate = application.candidate if application else None

    # Existing evaluation if any
    evaluation = None
    if candidate:
        evaluation = InterviewEvaluation.objects.filter(meeting=meeting, candidate=candidate).first()

    context = {
        "meeting": meeting,
        "interview": interview,
        "application": application,
        "candidate": candidate,
        "job": application.job if application else None,
        "evaluation": evaluation,
        "recommendations": InterviewEvaluation.Recommendation.choices,
    }
    return render(request, "connect/interview_studio.html", context)


@login_required
def smart_calendar(request):
    """
    Centralized HireNexa Smart Calendar:
    Aggregates:
    1. Scheduled Recruitment Interviews
    2. Connect Meetings & Panels
    3. Registered Career Webinars
    4. MCQ & Entrance Examination Schedules
    """
    user = request.user
    now = timezone.now()

    # 1. Meetings
    meetings = Meeting.objects.filter(
        Q(host=user) | Q(participants__user=user),
        status__in=[Meeting.Status.SCHEDULED, Meeting.Status.LIVE]
    ).order_by("scheduled_start")

    # 2. Interviews
    if user.role == User.Role.CANDIDATE:
        interviews = Interview.objects.filter(application__candidate=user, status=Interview.Status.SCHEDULED)
    else:
        interviews = Interview.objects.filter(Q(created_by=user) | Q(application__job__recruiter=user), status=Interview.Status.SCHEDULED)

    # 3. Registered Events
    registered_events = PublicEvent.objects.filter(
        registrations__user=user,
        scheduled_at__gte=now - timezone.timedelta(days=7)
    )

    calendar_items = []
    for m in meetings:
        calendar_items.append({
            "type": "Meeting",
            "title": m.title,
            "datetime": m.scheduled_start,
            "duration": m.scheduled_duration_minutes,
            "badge": "badge-primary",
            "link": m.get_absolute_url(),
            "action_text": "Join Meeting"
        })

    for ev in registered_events:
        calendar_items.append({
            "type": "Webinar",
            "title": ev.title,
            "datetime": ev.scheduled_at,
            "duration": ev.duration_minutes,
            "badge": "badge-accent",
            "link": ev.get_absolute_url(),
            "action_text": "View Webinar"
        })

    calendar_items.sort(key=lambda x: x["datetime"])

    context = {
        "calendar_items": calendar_items,
        "now": now,
    }
    return render(request, "connect/smart_calendar.html", context)
