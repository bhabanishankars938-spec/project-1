import logging
from datetime import datetime, time
from typing import Dict, Any, Optional
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from accounts.models import User, NotificationPreference
from recruitment.models import Notification

logger = logging.getLogger(__name__)


class PersonalizedNotificationEngine:
    """
    HireNexa Intelligent Personalized Notification Engine.
    Dispatches targeted alerts while strictly respecting user channel preferences,
    delivery digest schedules, and quiet hours.
    """

    @classmethod
    def is_in_quiet_hours(cls, prefs: NotificationPreference) -> bool:
        """Checks if current local time falls within candidate's configured quiet hours."""
        if not prefs.quiet_hours_enabled or not prefs.quiet_hours_start or not prefs.quiet_hours_end:
            return False

        now_time = timezone.localtime().time()
        start = prefs.quiet_hours_start
        end = prefs.quiet_hours_end

        if start <= end:
            return start <= now_time <= end
        else:
            # Over midnight window (e.g. 22:00 to 07:00)
            return now_time >= start or now_time <= end

    @classmethod
    def dispatch(
        cls,
        user: User,
        title: str,
        message: str,
        notification_type: str = Notification.Type.SYSTEM,
        link: str = "",
        category: str = "SYSTEM",  # JOBS, APPLICATIONS, INTERVIEWS, LEARNING, EXAMS, COMPANY
        is_urgent: bool = False,
    ) -> Dict[str, Any]:
        """
        Main entry point for dispatching a notification to a user.
        Evaluates user's NotificationPreference for in-app and email channels.
        """
        prefs = getattr(user, "notif_preferences", None)
        if not prefs:
            prefs, _ = NotificationPreference.objects.get_or_create(user=user)

        # Check quiet hours (urgent alerts like OTP or confirmed interview changes bypass quiet hours)
        in_quiet = cls.is_in_quiet_hours(prefs)
        if in_quiet and not is_urgent:
            logger.info("Notification '%s' for user %s suppressed due to active quiet hours.", title, user.username)
            return {"dispatched": False, "reason": "QUIET_HOURS"}

        # Determine in-app eligibility
        can_inapp = True
        if category == "JOBS" and not prefs.inapp_job_alerts:
            can_inapp = False
        elif category == "APPLICATIONS" and not prefs.inapp_applications:
            can_inapp = False
        elif category == "INTERVIEWS" and not prefs.inapp_interviews:
            can_inapp = False
        elif category == "NEWS" and not prefs.inapp_news:
            can_inapp = False

        # Determine email eligibility
        can_email = bool(user.email)
        if category == "JOBS" and not prefs.email_job_alerts:
            can_email = False
        elif category == "APPLICATIONS" and not prefs.email_applications:
            can_email = False
        elif category == "INTERVIEWS" and not prefs.email_interviews:
            can_email = False
        elif category == "NEWS" and not prefs.email_news:
            can_email = False

        inapp_created = False
        if can_inapp:
            Notification.objects.create(
                recipient=user,
                title=title,
                message=message,
                notification_type=notification_type,
                link=link,
            )
            inapp_created = True

        email_sent = False
        if can_email and prefs.digest_frequency == "INSTANT":
            try:
                send_mail(
                    subject=f"[HireNexa] {title}",
                    message=f"{message}\n\nView on HireNexa: {link}",
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "notifications@hirenexa.com"),
                    recipient_list=[user.email],
                    fail_silently=True,
                )
                email_sent = True
            except Exception as e:
                logger.error("Failed to dispatch notification email to %s: %s", user.email, e)

        return {
            "dispatched": inapp_created or email_sent,
            "inapp_created": inapp_created,
            "email_sent": email_sent,
            "user_id": user.id,
        }

    # =========================================================================
    # PRE-CONFIGURED SCENARIO DISPATCHERS
    # =========================================================================

    @classmethod
    def notify_relevant_job(cls, user: User, job_title: str, company_name: str, match_pct: int, job_id: int):
        """Notifies candidate about a newly posted job matching their skills."""
        title = f"New Job Match ({match_pct}%): {job_title}"
        msg = f"{company_name} is actively hiring for '{job_title}' with requirements matching your profile."
        return cls.dispatch(
            user=user,
            title=title,
            message=msg,
            notification_type=Notification.Type.APPLICATION,
            link=f"/jobs/{job_id}/",
            category="JOBS",
        )

    @classmethod
    def notify_application_update(cls, user: User, job_title: str, new_status_label: str, app_id: int):
        """Notifies candidate when application status changes in the pipeline."""
        title = f"Application Update: {job_title}"
        msg = f"Your application status has advanced to: {new_status_label}."
        return cls.dispatch(
            user=user,
            title=title,
            message=msg,
            notification_type=Notification.Type.STATUS_UPDATE,
            link=f"/candidate/dashboard/",
            category="APPLICATIONS",
            is_urgent=True,
        )

    @classmethod
    def notify_interview_schedule(cls, user: User, round_name: str, date_str: str, mode: str, interview_id: int):
        """Notifies candidate or interviewer of a scheduled interview round."""
        title = f"Interview Scheduled: {round_name}"
        msg = f"Your {round_name} has been confirmed for {date_str} ({mode}). Please review requirements in advance."
        return cls.dispatch(
            user=user,
            title=title,
            message=msg,
            notification_type=Notification.Type.INTERVIEW,
            link=f"/candidate/dashboard/",
            category="INTERVIEWS",
            is_urgent=True,
        )

    @classmethod
    def notify_exam_reminder(cls, user: User, exam_title: str, days_since: int):
        """Notifies candidate to review and maintain syllabus mastery via spaced repetition."""
        title = f"Exam Practice Reminder: {exam_title}"
        msg = f"You haven't practiced {exam_title} in {days_since} days. Strengthen your placement readiness today."
        return cls.dispatch(
            user=user,
            title=title,
            message=msg,
            notification_type=Notification.Type.SYSTEM,
            link="/assessments/coach/",
            category="EXAMS",
        )

    @classmethod
    def notify_learning_recommendation(cls, user: User, topic_name: str, reason: str):
        """Notifies candidate about an AI-recommended learning activity based on skill gaps."""
        title = f"Recommended Study Unit: {topic_name}"
        msg = f"{reason} Review verified learning notes and solve practice problems."
        return cls.dispatch(
            user=user,
            title=title,
            message=msg,
            notification_type=Notification.Type.SYSTEM,
            link="/assessments/coach/",
            category="LEARNING",
        )
