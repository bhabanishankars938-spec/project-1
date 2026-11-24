from django.contrib import admin
from .models import AIConversation, AIMessage, AIMessageAttachment, AIUsageLog


class AIMessageAttachmentInline(admin.TabularInline):
    model = AIMessageAttachment
    extra = 0
    readonly_fields = ("file_name", "file_type", "file_size", "mime_type", "uploaded_at")


class AIMessageInline(admin.StackedInline):
    model = AIMessage
    extra = 0
    fields = ("role", "content", "reasoning", "feedback", "token_count", "created_at")
    readonly_fields = ("created_at",)


@admin.register(AIConversation)
class AIConversationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "mode", "language", "is_pinned", "created_at", "updated_at")
    list_filter = ("mode", "language", "is_pinned", "created_at")
    search_fields = ("title", "user__username", "user__email", "session_key")
    inlines = [AIMessageInline]


@admin.register(AIMessage)
class AIMessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "role", "feedback", "token_count", "is_voice", "created_at")
    list_filter = ("role", "feedback", "is_voice", "created_at")
    search_fields = ("content", "conversation__title", "conversation__user__username")
    inlines = [AIMessageAttachmentInline]


@admin.register(AIMessageAttachment)
class AIMessageAttachmentAdmin(admin.ModelAdmin):
    list_display = ("file_name", "file_type", "file_size", "mime_type", "uploaded_at")
    list_filter = ("file_type", "uploaded_at")
    search_fields = ("file_name", "extracted_text")


@admin.register(AIUsageLog)
class AIUsageLogAdmin(admin.ModelAdmin):
    list_display = ("user", "provider", "model_name", "total_tokens", "latency_ms", "status", "timestamp")
    list_filter = ("provider", "status", "timestamp")
    search_fields = ("user__username", "model_name", "error_message")
