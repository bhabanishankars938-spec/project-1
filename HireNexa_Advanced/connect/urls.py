from django.urls import path
from . import views, api_views

app_name = "connect"

urlpatterns = [
    # Dashboard & Core Modules
    path("", views.connect_dashboard, name="dashboard"),
    path("my-meetings/", views.my_meetings, name="my_meetings"),
    path("interviews/", views.upcoming_interviews, name="upcoming_interviews"),
    path("upcoming-interviews/", views.upcoming_interviews, name="upcoming_interviews_alias"),
    path("instant/", views.instant_meeting_create, name="instant_meeting"),
    path("schedule/", views.schedule_meeting, name="schedule_meeting"),
    path("join/", views.join_meeting_view, name="join_meeting"),
    path("join/<str:meeting_id>/", views.join_meeting_direct, name="join_meeting_direct"),
    path("start/<str:meeting_id>/", views.start_meeting, name="start_meeting"),
    path("room/<str:meeting_id>/", views.meeting_room, name="meeting_room"),
    path("history/", views.meeting_history, name="meeting_history"),
    path("settings/", views.meeting_settings, name="meeting_settings"),
    path("studio/<str:meeting_id>/", views.interview_studio, name="interview_studio"),
    path("calendar/", views.smart_calendar, name="smart_calendar"),
    path("share/<str:meeting_id>/", views.meeting_share_info_api, name="meeting_share_info"),

    # Public Moderated Events & Webinars
    path("events/", views.public_events, name="public_events"),
    path("events/<slug:slug>/", views.public_event_detail, name="public_event_detail"),
    path("events/<slug:slug>/register/", views.public_event_register, name="public_event_register"),
    path("events/<slug:slug>/stage/", views.public_event_room, name="public_event_room"),

    # REST / AJAX Real-time WebRTC, Invitations & Moderation APIs
    path("api/<str:meeting_id>/invite/", views.send_meeting_invitation_api, name="api_send_invitation"),
    path("api/<str:meeting_id>/admit/", views.admit_participant_api, name="api_admit_participant"),
    path("api/<str:meeting_id>/waiting-status/", views.check_waiting_status_api, name="api_waiting_status"),
    path("api/<str:meeting_id>/signal/", api_views.meeting_signal_api, name="api_signal"),
    path("api/<str:meeting_id>/moderation/", api_views.host_moderation_api, name="api_host_moderation"),
    path("api/<str:meeting_id>/evaluation/", api_views.submit_interview_evaluation_api, name="api_submit_evaluation"),
    path("api/<str:meeting_id>/abuse/", api_views.report_abuse_api, name="api_report_abuse"),
    path("api/<str:meeting_id>/ai-summary/", api_views.ai_meeting_notes_summary_api, name="api_ai_summary"),
    path("api/ai/questions/", api_views.ai_question_generator_api, name="api_ai_questions"),
]
