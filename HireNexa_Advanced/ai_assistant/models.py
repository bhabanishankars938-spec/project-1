import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class AIConversation(models.Model):
    class Mode(models.TextChoices):
        GENERAL = "GENERAL", "General AI Assistant"
        CODING = "CODING", "Advanced Coding Assistant"
        CAREER = "CAREER", "Career & Job Assistant"
        DOCS = "DOCS", "Document & Screenshot Analysis"

    class Language(models.TextChoices):
        ENGLISH = "en", "English"
        HINDI = "hi", "Hindi (हिन्दी)"
        ODIA = "or", "Odia (ଓଡ଼ିଆ)"
        HINGLISH = "hinglish", "Hinglish (Hindi in Roman)"
        SIMPLE_EN = "simple_en", "Simple English"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ai_conversations",
        help_text="Authenticated owner of this conversation. Null for guest visitors.",
    )
    session_key = models.CharField(
        max_length=80,
        blank=True,
        db_index=True,
        help_text="Browser session key for non-authenticated guests.",
    )
    title = models.CharField(max_length=220, default="New Conversation")
    mode = models.CharField(max_length=30, choices=Mode.choices, default=Mode.GENERAL)
    language = models.CharField(max_length=20, choices=Language.choices, default=Language.ENGLISH)
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "-updated_at"]
        verbose_name = "AI Conversation"
        verbose_name_plural = "AI Conversations"

    def __str__(self):
        user_label = self.user.username if self.user else f"Guest ({self.session_key[:8]})"
        return f"[{self.get_mode_display()}] {self.title} ({user_label})"

    @property
    def message_count(self):
        return self.messages.count()

    @property
    def last_message(self):
        return self.messages.order_by("-created_at").first()


class AIMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"
        SYSTEM = "system", "System"

    class Feedback(models.TextChoices):
        NONE = "none", "No Feedback"
        LIKE = "like", "Helpful / Upvoted"
        DISLIKE = "dislike", "Not Helpful / Downvoted"

    conversation = models.ForeignKey(
        AIConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.USER)
    content = models.TextField(help_text="Markdown formatted message content")
    reasoning = models.TextField(blank=True, help_text="Step-by-step thinking or reasoning trace")
    tools_used = models.JSONField(
        default=list,
        blank=True,
        help_text="Structured HireNexa platform tool execution payloads and results",
    )
    citations = models.JSONField(
        default=list,
        blank=True,
        help_text="Web research citations with verified source URLs and titles",
    )
    feedback = models.CharField(max_length=20, choices=Feedback.choices, default=Feedback.NONE)
    token_count = models.IntegerField(default=0)
    is_voice = models.BooleanField(default=False, help_text="Sent using speech-to-text voice input")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "AI Message"
        verbose_name_plural = "AI Messages"

    def __str__(self):
        return f"{self.role.upper()} in conv #{self.conversation_id}: {self.content[:40]}..."


class AIMessageAttachment(models.Model):
    class FileType(models.TextChoices):
        IMAGE = "image", "Image / Screenshot (PNG, JPG, WEBP)"
        DOCUMENT = "document", "Document (PDF, DOCX, TXT)"

    message = models.ForeignKey(
        AIMessage,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
    )
    file = models.FileField(upload_to="ai_attachments/%Y/%m/")
    file_type = models.CharField(max_length=20, choices=FileType.choices)
    file_name = models.CharField(max_length=255)
    file_size = models.IntegerField(default=0, help_text="Size in bytes")
    mime_type = models.CharField(max_length=100)
    extracted_text = models.TextField(blank=True, help_text="Extracted text from PDF, DOCX, or OCR")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]
        verbose_name = "AI Message Attachment"
        verbose_name_plural = "AI Message Attachments"

    def __str__(self):
        return f"{self.file_type}: {self.file_name} ({self.file_size} bytes)"


class AIUsageLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_usage_logs",
    )
    conversation = models.ForeignKey(
        AIConversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usage_logs",
    )
    provider = models.CharField(max_length=50, default="gemini")
    model_name = models.CharField(max_length=80, default="gemini-2.0-flash")
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    latency_ms = models.IntegerField(default=0)
    status = models.CharField(max_length=30, default="SUCCESS")
    error_message = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "AI Usage Log"
        verbose_name_plural = "AI Usage Logs"

    def __str__(self):
        actor = self.user.username if self.user else "Guest"
        return f"[{self.timestamp:%Y-%m-%d %H:%M:%S}] {actor} - {self.model_name} ({self.total_tokens} tokens)"
