import json
import logging
import uuid
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .ai_service import AIService
from .file_processor import FileProcessorService
from .models import AIConversation, AIMessage, AIMessageAttachment, AIUsageLog
from .tools import HireNexaToolRegistry

logger = logging.getLogger(__name__)


def _get_user_or_session(request):
    """Returns (user, session_key). Ensures session exists for anonymous users."""
    user = request.user if request.user.is_authenticated else None
    if not request.session.session_key:
        request.session.save()
    session_key = request.session.session_key or ""
    return user, session_key


def _get_conversation_queryset(request):
    """Enforces strict user/session isolation on conversations."""
    user, session_key = _get_user_or_session(request)
    if user:
        return AIConversation.objects.filter(user=user)
    else:
        return AIConversation.objects.filter(user__isnull=True, session_key=session_key)


# ==============================================================================
# 1. PRIMARY UI PAGE
# ==============================================================================

@ensure_csrf_cookie
def ai_assistant_view(request):
    """
    Renders the flagship HireNexa AI Assistant workspace interface.
    """
    user, session_key = _get_user_or_session(request)
    conversations = _get_conversation_queryset(request)[:30]
    
    # Active conversation UUID from query param or most recent
    active_uuid = request.GET.get("c")
    active_conversation = None
    if active_uuid:
        active_conversation = _get_conversation_queryset(request).filter(uuid=active_uuid).first()

    status_data = AIService.get_status()

    context = {
        "conversations": conversations,
        "active_conversation": active_conversation,
        "is_configured": status_data["is_configured"],
        "primary_provider": status_data["primary_provider"],
        "primary_model": status_data["primary_model"],
        "primary_status": status_data["primary_status"],
        "fallback_provider": status_data["fallback_provider"],
        "fallback_model": status_data["fallback_model"],
        "fallback_status": status_data["fallback_status"],
        "available_modes": AIConversation.Mode.choices,
        "available_languages": AIConversation.Language.choices,
    }
    return render(request, "ai_assistant/chat.html", context)


# ==============================================================================
# 2. CONVERSATION MANAGEMENT API
# ==============================================================================

@require_GET
def conversation_list_api(request):
    """Returns user's conversations with optional search query."""
    q = request.GET.get("q", "").strip()
    qs = _get_conversation_queryset(request)
    if q:
        qs = qs.filter(title__icontains=q)

    data = []
    for conv in qs[:40]:
        data.append({
            "uuid": str(conv.uuid),
            "title": conv.title,
            "mode": conv.mode,
            "mode_display": conv.get_mode_display(),
            "language": conv.language,
            "is_pinned": conv.is_pinned,
            "created_at": conv.created_at.strftime("%b %d, %Y"),
            "updated_at": conv.updated_at.strftime("%b %d, %Y · %I:%M %p"),
            "message_count": conv.messages.count(),
        })

    return JsonResponse({"success": True, "conversations": data})


@require_POST
def conversation_create_api(request):
    """Creates a fresh AI Conversation."""
    user, session_key = _get_user_or_session(request)
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        data = {}

    mode = data.get("mode", AIConversation.Mode.GENERAL)
    if mode not in dict(AIConversation.Mode.choices):
        mode = AIConversation.Mode.GENERAL

    lang = data.get("language", "en")
    title = data.get("title", "").strip() or "New Conversation"

    conv = AIConversation.objects.create(
        user=user,
        session_key=session_key if not user else "",
        mode=mode,
        language=lang,
        title=title,
    )

    return JsonResponse({
        "success": True,
        "conversation": {
            "uuid": str(conv.uuid),
            "title": conv.title,
            "mode": conv.mode,
            "mode_display": conv.get_mode_display(),
            "language": conv.language,
            "created_at": conv.created_at.strftime("%b %d, %Y"),
        }
    })


@require_GET
def conversation_detail_api(request, conv_uuid):
    """Retrieves full conversation transcript with attachments, tools, and citations."""
    conv = get_object_or_404(_get_conversation_queryset(request), uuid=conv_uuid)
    messages_qs = conv.messages.all().prefetch_related("attachments")

    messages_data = []
    for m in messages_qs:
        attachments_data = []
        for att in m.attachments.all():
            attachments_data.append({
                "id": att.id,
                "file_type": att.file_type,
                "file_name": att.file_name,
                "file_size": att.file_size,
                "file_url": att.file.url if att.file else "",
            })

        messages_data.append({
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "reasoning": m.reasoning,
            "tools_used": m.tools_used,
            "citations": m.citations,
            "feedback": m.feedback,
            "is_voice": m.is_voice,
            "token_count": m.token_count,
            "created_at": m.created_at.strftime("%I:%M %p"),
            "attachments": attachments_data,
        })

    return JsonResponse({
        "success": True,
        "conversation": {
            "uuid": str(conv.uuid),
            "title": conv.title,
            "mode": conv.mode,
            "mode_display": conv.get_mode_display(),
            "language": conv.language,
            "is_pinned": conv.is_pinned,
            "messages": messages_data,
        }
    })


@require_POST
def conversation_rename_api(request, conv_uuid):
    """Renames an existing conversation title."""
    conv = get_object_or_404(_get_conversation_queryset(request), uuid=conv_uuid)
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        data = {}

    new_title = (data.get("title") or "").strip()
    if not new_title:
        return JsonResponse({"success": False, "error": "Title cannot be empty."}, status=400)

    conv.title = new_title[:200]
    conv.save()
    return JsonResponse({"success": True, "title": conv.title})


@require_POST
def conversation_delete_api(request, conv_uuid):
    """Permanently deletes a conversation and all its messages."""
    conv = get_object_or_404(_get_conversation_queryset(request), uuid=conv_uuid)
    conv.delete()
    return JsonResponse({"success": True, "message": "Conversation deleted."})


@require_POST
def conversation_clear_all_api(request):
    """Deletes all conversations belonging to the active user/session."""
    qs = _get_conversation_queryset(request)
    count = qs.count()
    qs.delete()
    return JsonResponse({"success": True, "deleted_count": count})


# ==============================================================================
# 3. REAL-TIME STREAMING CHAT (SSE)
# ==============================================================================

def chat_stream_view(request, conv_uuid):
    """
    Streaming Server-Sent Events (SSE) chat endpoint.
    Accepts user message, processes multimodal attachments, triggers platform tools,
    and streams tokens to frontend in real time.
    """
    conv = get_object_or_404(_get_conversation_queryset(request), uuid=conv_uuid)
    user, session_key = _get_user_or_session(request)

    if request.method != "POST":
        return JsonResponse({"error": "POST method required"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)

    user_text = (payload.get("message") or "").strip()
    mode = payload.get("mode", conv.mode)
    language = payload.get("language", conv.language)
    enable_web_research = bool(payload.get("enable_web_research", False))
    is_voice = bool(payload.get("is_voice", False))
    attachment_ids = payload.get("attachment_ids", [])

    if not user_text and not attachment_ids:
        return JsonResponse({"error": "Message or attachment is required."}, status=400)

    # Update conversation settings if changed
    if mode != conv.mode or language != conv.language:
        conv.mode = mode
        conv.language = language
        conv.save(update_fields=["mode", "language", "updated_at"])

    # 1. Create and persist User Message
    user_msg = AIMessage.objects.create(
        conversation=conv,
        role=AIMessage.Role.USER,
        content=user_text,
        is_voice=is_voice,
    )

    # 2. Associate uploaded attachments and extract text / base64
    image_attachment = None
    document_text_blocks = []
    
    if attachment_ids:
        attachments = AIMessageAttachment.objects.filter(id__in=attachment_ids, message__isnull=True)
        for att in attachments:
            att.message = user_msg
            att.save()

            if att.file_type == AIMessageAttachment.FileType.IMAGE and not image_attachment:
                try:
                    image_attachment = FileProcessorService.process_image_attachment(att.file)
                except Exception as e:
                    logger.error("Error loading image attachment: %s", e)
            elif att.extracted_text:
                document_text_blocks.append(f"[{att.file_name}]:\n{att.extracted_text}")

    combined_doc_text = "\n\n".join(document_text_blocks)

    # 3. Retrieve conversation history for context
    history_messages = []
    for past_msg in conv.messages.filter(id__lt=user_msg.id).order_by("-created_at")[:8]:
        history_messages.insert(0, {
            "role": past_msg.role,
            "content": past_msg.content,
        })

    # Auto-generate title if this is the first message
    if conv.title == "New Conversation" and user_text:
        words = user_text.split()
        conv.title = " ".join(words[:6]).title()
        if len(words) > 6:
            conv.title += "..."
        conv.save(update_fields=["title"])

    # Generator for Streaming Response
    def event_generator():
        accumulated_text = []
        tools_executed = []
        citations_found = []

        stream = AIService.generate_response_stream(
            conversation_history=history_messages,
            user_message=user_text,
            user=user,
            mode=mode,
            language=language,
            image_attachment=image_attachment,
            document_text=combined_doc_text,
            enable_web_research=enable_web_research,
        )

        for sse_event in stream:
            # Parse payload to accumulate text and tools for database persistence
            try:
                line_data = sse_event.replace("data: ", "").strip()
                if line_data:
                    parsed = json.loads(line_data)
                    etype = parsed.get("type")
                    if etype == "token":
                        accumulated_text.append(parsed.get("data", ""))
                    elif etype == "tool":
                        tools_executed.append(parsed.get("data", {}))
                    elif etype == "citations":
                        citations_found.extend(parsed.get("data", []))
            except Exception:
                pass

            yield sse_event

        # Save Assistant response message to DB
        full_content = "".join(accumulated_text).strip()
        if not full_content and tools_executed:
            tool_names = [t.get("tool", "action") for t in tools_executed]
            full_content = f"Retrieved platform data for: {', '.join(tool_names)}."

        if full_content:
            ai_msg = AIMessage.objects.create(
                conversation=conv,
                role=AIMessage.Role.ASSISTANT,
                content=full_content,
                tools_used=tools_executed,
                citations=citations_found,
                token_count=len(full_content.split()),
            )
            # Log usage
            status_data = AIService.get_status()
            AIUsageLog.objects.create(
                user=user,
                conversation=conv,
                provider=status_data.get("primary_provider", "openai"),
                model_name=status_data.get("primary_model", "gpt-4o-mini"),
                prompt_tokens=len(user_text.split()),
                completion_tokens=len(full_content.split()),
                total_tokens=len(user_text.split()) + len(full_content.split()),
            )

    response = StreamingHttpResponse(event_generator(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


# ==============================================================================
# 4. SECURE FILE & ATTACHMENT UPLOAD API
# ==============================================================================

@require_POST
def file_upload_api(request):
    """
    Accepts user uploaded documents (PDF, DOCX, TXT) and images (PNG, JPG, WEBP).
    Validates, extracts text, and stores attachment record.
    """
    if "file" not in request.FILES:
        return JsonResponse({"success": False, "error": "No file uploaded."}, status=400)

    uploaded_file = request.FILES["file"]
    is_valid, file_type, err = FileProcessorService.validate_file(uploaded_file)
    if not is_valid:
        return JsonResponse({"success": False, "error": err}, status=400)

    extracted_text = ""
    if file_type == "document":
        try:
            extracted_text = FileProcessorService.extract_document_text(uploaded_file)
        except Exception as e:
            logger.error("Text extraction failed for %s: %s", uploaded_file.name, e)

    # Save attachment
    attachment = AIMessageAttachment.objects.create(
        message=None,  # Will be attached when message is posted
        file=uploaded_file,
        file_type=file_type,
        file_name=uploaded_file.name,
        file_size=uploaded_file.size,
        mime_type=uploaded_file.content_type or "application/octet-stream",
        extracted_text=extracted_text,
    )

    return JsonResponse({
        "success": True,
        "attachment": {
            "id": attachment.id,
            "file_type": attachment.file_type,
            "file_name": attachment.file_name,
            "file_size": attachment.file_size,
            "file_url": attachment.file.url if attachment.file else "",
            "extracted_length": len(extracted_text),
        }
    })


# ==============================================================================
# 5. USER FEEDBACK & DIAGNOSTICS
# ==============================================================================

@require_POST
def message_feedback_api(request, message_id):
    """Sets thumbs up / down feedback for an AI response."""
    msg = get_object_or_404(AIMessage, id=message_id, role=AIMessage.Role.ASSISTANT)
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        data = {}

    fb = data.get("feedback")
    if fb in ["like", "dislike", "none"]:
        msg.feedback = fb
        msg.save(update_fields=["feedback"])
        return JsonResponse({"success": True, "feedback": msg.feedback})

    return JsonResponse({"success": False, "error": "Invalid feedback type."}, status=400)


@require_GET
def ai_status_api(request):
    """Returns AI Assistant hybrid provider health and tools catalog."""
    status_data = AIService.get_status()
    tools = HireNexaToolRegistry.get_tool_definitions(user=request.user)
    return JsonResponse({
        "success": True,
        **status_data,
        "tools_available_count": len(tools),
        "tools": [t["name"] for t in tools],
    })


