from django.urls import path
from . import views

urlpatterns = [
    # Flagship UI Workspace
    path("", views.ai_assistant_view, name="ai_assistant"),
    path("chat/", views.ai_assistant_view, name="ai_assistant_chat"),

    # REST APIs & Streaming
    path("api/conversations/", views.conversation_list_api, name="ai_conversation_list"),
    path("api/conversations/create/", views.conversation_create_api, name="ai_conversation_create"),
    path("api/conversations/<uuid:conv_uuid>/", views.conversation_detail_api, name="ai_conversation_detail"),
    path("api/conversations/<uuid:conv_uuid>/rename/", views.conversation_rename_api, name="ai_conversation_rename"),
    path("api/conversations/<uuid:conv_uuid>/delete/", views.conversation_delete_api, name="ai_conversation_delete"),
    path("api/conversations/clear/", views.conversation_clear_all_api, name="ai_conversation_clear_all"),
    path("api/conversations/<uuid:conv_uuid>/stream/", views.chat_stream_view, name="ai_chat_stream"),
    path("api/upload/", views.file_upload_api, name="ai_file_upload"),
    path("api/messages/<int:message_id>/feedback/", views.message_feedback_api, name="ai_message_feedback"),
    path("api/status/", views.ai_status_api, name="ai_status_api"),
]
