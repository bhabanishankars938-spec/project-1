from django.contrib import admin
from .models import (
    Meeting, MeetingParticipant, MeetingChatMessage,
    PublicEvent, EventRegistration, InterviewEvaluation, MeetingAbuseReport
)


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ["meeting_id", "title", "meeting_type", "status", "host", "scheduled_start", "is_locked"]
    list_filter = ["meeting_type", "status", "is_locked", "scheduled_start"]
    search_fields = ["meeting_id", "title", "host__username", "host__email"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(MeetingParticipant)
class MeetingParticipantAdmin(admin.ModelAdmin):
    list_display = ["meeting", "display_name", "role", "status", "joined_at", "left_at"]
    list_filter = ["role", "status"]
    search_fields = ["meeting__meeting_id", "user__username", "guest_name", "guest_email"]


@admin.register(MeetingChatMessage)
class MeetingChatMessageAdmin(admin.ModelAdmin):
    list_display = ["meeting", "sender_name", "message_type", "is_approved", "created_at"]
    list_filter = ["message_type", "is_approved", "created_at"]
    search_fields = ["meeting__meeting_id", "sender_name", "content"]


@admin.register(PublicEvent)
class PublicEventAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "scheduled_at", "status", "is_published", "registered_count"]
    list_filter = ["category", "status", "is_published", "scheduled_at"]
    search_fields = ["title", "presenter_name", "description"]
    prepopulated_fields = {"slug": ("title",)}


@admin.register(EventRegistration)
class EventRegistrationAdmin(admin.ModelAdmin):
    list_display = ["event", "user", "registered_at", "attended", "feedback_rating"]
    list_filter = ["attended", "feedback_rating", "registered_at"]
    search_fields = ["event__title", "user__username", "user__email"]


@admin.register(InterviewEvaluation)
class InterviewEvaluationAdmin(admin.ModelAdmin):
    list_display = ["meeting", "candidate", "evaluator", "recommendation", "overall_score", "created_at"]
    list_filter = ["recommendation", "created_at"]
    search_fields = ["meeting__meeting_id", "candidate__username", "evaluator__username"]


@admin.register(MeetingAbuseReport)
class MeetingAbuseReportAdmin(admin.ModelAdmin):
    list_display = ["meeting", "reporter", "offender", "reason", "is_reviewed", "created_at"]
    list_filter = ["is_reviewed", "reason", "created_at"]
    search_fields = ["meeting__meeting_id", "reporter__username", "details"]
