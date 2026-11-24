import time
import html
from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.core.cache import cache
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status

from accounts.models import User
from .models import (
    Meeting, MeetingParticipant, MeetingChatMessage,
    InterviewEvaluation, MeetingAbuseReport, PublicEvent
)
from .ai_service import AIInterviewIntelligenceService


@api_view(["GET", "POST"])
def meeting_signal_api(request, meeting_id):
    """
    Real-time WebRTC Signaling & State Exchange for HireNexa Connect.
    Transfers SDP offers, SDP answers, ICE candidates, chat, and presence.
    Supports low-latency polling backed by Django Cache with bounded FIFO buffer.
    """
    meeting = get_object_or_404(Meeting, meeting_id=meeting_id)

    # Check meeting status
    if meeting.status in [Meeting.Status.COMPLETED, Meeting.Status.CANCELLED]:
        return Response({
            "success": False,
            "error": "This meeting has ended.",
            "meeting_ended": True
        }, status=status.HTTP_410_GONE)

    username = request.user.username if request.user.is_authenticated else f"guest_{request.session.session_key or 'anon'}"
    display_name = request.user.get_full_name() or request.user.username if request.user.is_authenticated else "Guest Attendee"

    # Determine user role in this meeting
    is_host = bool(request.user.is_authenticated and (meeting.host == request.user or request.user.is_superuser))
    participant = None
    if request.user.is_authenticated:
        participant = MeetingParticipant.objects.filter(meeting=meeting, user=request.user).first()

    role_label = "Host" if is_host else (participant.get_role_display() if participant else "Attendee")

    cache_key = f"hnx_signals_{meeting.meeting_id}"
    signals = cache.get(cache_key) or []

    presence_key = f"hnx_presence_{meeting.meeting_id}"
    presence = cache.get(presence_key) or {}

    now_ts = time.time()

    # Heartbeat presence update
    presence[username] = {
        "username": username,
        "name": display_name,
        "role": role_label,
        "is_host": is_host,
        "last_seen": now_ts,
        "audio_muted": participant.audio_muted if participant else False,
        "video_muted": participant.video_muted if participant else False,
        "hand_raised": participant.hand_raised if participant else False,
    }
    # Purge participants not seen in last 25 seconds
    active_presence = {
        u: p for u, p in presence.items() if (now_ts - p.get("last_seen", 0)) < 25
    }
    cache.set(presence_key, active_presence, timeout=7200)

    # POST: Broadcast new WebRTC or chat signal
    if request.method == "POST":
        signal_type = request.data.get("type", "message")
        payload = request.data.get("payload", {})
        target = request.data.get("target", "all")  # target participant or "all"

        # Sanitize chat messages
        if signal_type == "chat":
            raw_text = str(payload.get("text", "")).strip()
            if not raw_text:
                return Response({"error": "Empty message"}, status=status.HTTP_400_BAD_REQUEST)
            clean_text = html.escape(raw_text)
            payload["text"] = clean_text

            # Persist chat message for meeting audit
            MeetingChatMessage.objects.create(
                meeting=meeting,
                sender=request.user if request.user.is_authenticated else None,
                sender_name=display_name,
                sender_role=role_label,
                message_type=MeetingChatMessage.MessageType.CHAT,
                content=clean_text
            )

        new_signal = {
            "id": len(signals) + 1,
            "sender": username,
            "sender_name": display_name,
            "sender_role": role_label,
            "is_host": is_host,
            "type": signal_type,
            "target": target,
            "payload": payload,
            "timestamp": now_ts,
        }
        signals.append(new_signal)
        # Keep last 200 signals
        cache.set(cache_key, signals[-200:], timeout=7200)

        return Response({
            "success": True,
            "signal_id": new_signal["id"],
            "active_participants": len(active_presence)
        })

    # GET: Fetch incoming signals since last received ID
    since_id = int(request.GET.get("since", 0))
    exclude_self = request.GET.get("exclude_self", "true").lower() == "true"

    unseen = [
        s for s in signals
        if s["id"] > since_id and (not exclude_self or s["sender"] != username) and (s["target"] in ["all", username])
    ]

    return Response({
        "success": True,
        "signals": unseen,
        "presence": list(active_presence.values()),
        "participant_count": len(active_presence),
        "is_locked": meeting.is_locked,
        "meeting_status": meeting.status
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def host_moderation_api(request, meeting_id):
    """
    Host meeting control endpoint:
    Actions: 'mute_all', 'mute_user', 'kick_user', 'lower_hand', 'lock_room', 'end_meeting'
    """
    meeting = get_object_or_404(Meeting, meeting_id=meeting_id)

    # Permission check: User must be host or superuser
    if meeting.host != request.user and not request.user.is_superuser:
        return Response({"error": "Host privileges required for moderation."}, status=status.HTTP_403_FORBIDDEN)

    action = request.data.get("action")
    target_username = request.data.get("target_username")

    cache_key = f"hnx_signals_{meeting.meeting_id}"
    signals = cache.get(cache_key) or []

    if action == "lock_room":
        meeting.is_locked = not meeting.is_locked
        meeting.save(update_fields=["is_locked"])
        sys_msg = "Meeting has been locked by the host." if meeting.is_locked else "Meeting has been unlocked."
    elif action == "end_meeting":
        meeting.status = Meeting.Status.COMPLETED
        meeting.actual_end = timezone.now()
        meeting.save(update_fields=["status", "actual_end"])
        sys_msg = "Meeting was ended for all participants by the host."
    elif action == "kick_user" and target_username:
        sys_msg = f"Participant {target_username} was removed from the meeting."
        # Update participant record if exists
        target_u = User.objects.filter(username=target_username).first()
        if target_u:
            MeetingParticipant.objects.filter(meeting=meeting, user=target_u).update(status=MeetingParticipant.Status.REMOVED)
    elif action == "mute_user" and target_username:
        sys_msg = f"Host muted participant {target_username}."
    elif action == "mute_all":
        sys_msg = "Host muted all participants."
    else:
        sys_msg = f"Host action: {action}"

    # Push system action signal to room
    action_signal = {
        "id": len(signals) + 1,
        "sender": request.user.username,
        "sender_name": "Host Moderator",
        "sender_role": "Host",
        "is_host": True,
        "type": "host_action",
        "target": target_username or "all",
        "payload": {
            "action": action,
            "target": target_username,
            "message": sys_msg,
            "is_locked": meeting.is_locked,
            "meeting_ended": (meeting.status == Meeting.Status.COMPLETED)
        },
        "timestamp": time.time(),
    }
    signals.append(action_signal)
    cache.set(cache_key, signals[-200:], timeout=7200)

    return Response({
        "success": True,
        "action": action,
        "message": sys_msg,
        "is_locked": meeting.is_locked,
        "status": meeting.status
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ai_question_generator_api(request):
    """
    Generates intelligent interview questions using job description,
    candidate skills, and round name. Explainable and human-reviewed.
    """
    job_title = request.data.get("job_title", "Software Engineer")
    job_description = request.data.get("job_description", "")
    skills = request.data.get("skills", [])
    round_name = request.data.get("round_name", "Technical Round 1")

    res = AIInterviewIntelligenceService.generate_interview_questions(
        job_title=job_title,
        job_description=job_description,
        candidate_skills=skills,
        round_name=round_name
    )
    return Response(res)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ai_meeting_notes_summary_api(request, meeting_id):
    """
    Synthesizes interview notes into structured feedback rubric.
    """
    meeting = get_object_or_404(Meeting, meeting_id=meeting_id)
    notes = request.data.get("notes", "")
    round_name = request.data.get("round_name", meeting.get_interview_round_display())

    res = AIInterviewIntelligenceService.generate_meeting_summary(
        meeting_title=meeting.title,
        rough_notes=notes,
        round_name=round_name
    )
    return Response(res)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_interview_evaluation_api(request, meeting_id):
    """
    Submits structured scorecard and evaluation notes for an interview candidate.
    """
    meeting = get_object_or_404(Meeting, meeting_id=meeting_id)

    # Candidate identification
    candidate_id = request.data.get("candidate_id")
    candidate = None
    if candidate_id:
        candidate = User.objects.filter(id=candidate_id).first()
    elif meeting.interview and meeting.interview.application:
        candidate = meeting.interview.application.candidate

    if not candidate:
        # Check meeting participants
        cand_part = meeting.participants.filter(role=MeetingParticipant.Role.CANDIDATE).first()
        if cand_part and cand_part.user:
            candidate = cand_part.user

    if not candidate:
        return Response({"error": "Candidate record not identified for this interview."}, status=status.HTTP_400_BAD_REQUEST)

    tech_score = Decimal(str(request.data.get("technical_competency", 7.0)))
    prob_score = Decimal(str(request.data.get("problem_solving", 7.0)))
    comm_score = Decimal(str(request.data.get("communication_clarity", 7.0)))
    cult_score = Decimal(str(request.data.get("culture_and_values", 7.0)))
    overall = Decimal(str(request.data.get("overall_score", 7.0)))
    recommendation = request.data.get("recommendation", InterviewEvaluation.Recommendation.HIRE)
    notes = request.data.get("detailed_notes", "")
    strengths = request.data.get("strengths_observed", "")
    growth = request.data.get("areas_for_growth", "")
    ai_summary = request.data.get("ai_generated_summary", "")

    evaluation, _ = InterviewEvaluation.objects.update_or_create(
        meeting=meeting,
        candidate=candidate,
        evaluator=request.user,
        defaults={
            "interview": meeting.interview,
            "technical_competency": tech_score,
            "problem_solving": prob_score,
            "communication_clarity": comm_score,
            "culture_and_values": cult_score,
            "overall_score": overall,
            "recommendation": recommendation,
            "detailed_notes": notes,
            "strengths_observed": strengths,
            "areas_for_growth": growth,
            "ai_generated_summary": ai_summary,
        }
    )

    # Update recruitment interview status if linked
    if meeting.interview:
        meeting.interview.status = "COMPLETED"
        meeting.interview.interviewer_feedback = f"{recommendation}: {notes}"
        meeting.interview.save(update_fields=["status", "interviewer_feedback"])

    return Response({
        "success": True,
        "evaluation_id": evaluation.id,
        "recommendation": evaluation.get_recommendation_display(),
        "overall_score": str(evaluation.overall_score)
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def report_abuse_api(request, meeting_id):
    """
    Submits participant abuse report with incident details.
    """
    meeting = get_object_or_404(Meeting, meeting_id=meeting_id)
    reason = request.data.get("reason", "Disruptive Behavior")
    details = request.data.get("details", "").strip()
    offender_username = request.data.get("offender_username")

    offender = User.objects.filter(username=offender_username).first() if offender_username else None

    report = MeetingAbuseReport.objects.create(
        meeting=meeting,
        reporter=request.user,
        offender=offender,
        reason=reason,
        details=details
    )

    return Response({
        "success": True,
        "report_id": report.id,
        "message": "Abuse report submitted to trust & safety team. You may leave the meeting immediately."
    })
