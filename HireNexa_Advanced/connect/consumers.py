import json
import html
import time
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.cache import cache


class MeetingSignalConsumer(AsyncWebsocketConsumer):
    """
    Real-Time WebRTC WebSocket Signaling Consumer for HireNexa Connect.
    Handles peer SDP negotiation (offer/answer), ICE candidate exchange,
    real-time chat, and host moderation actions.
    """

    async def connect(self):
        self.meeting_id = self.scope["url_route"]["kwargs"]["meeting_id"]
        self.room_group_name = f"hnx_meeting_{self.meeting_id}"
        self.user = self.scope.get("user")

        # Validate authentication
        if not self.user or not self.user.is_authenticated:
            # Reject unauthenticated WebSocket connections for private rooms
            await self.close(code=4401)
            return

        # Verify meeting exists and is active
        meeting_valid = await self.verify_meeting(self.meeting_id)
        if not meeting_valid:
            await self.close(code=4404)
            return

        # Join the meeting broadcast channel group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Update presence
        await self.update_presence(is_online=True)

        # Notify participants of arrival
        display_name = self.user.get_full_name() or self.user.username
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "meeting_broadcast",
                "sender_channel": self.channel_name,
                "signal": {
                    "type": "user_joined",
                    "sender": self.user.username,
                    "sender_name": display_name,
                    "timestamp": time.time()
                }
            }
        )

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            # Update presence
            if hasattr(self, "user") and self.user.is_authenticated:
                await self.update_presence(is_online=False)

                # Broadcast departure
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "meeting_broadcast",
                        "sender_channel": self.channel_name,
                        "signal": {
                            "type": "user_left",
                            "sender": self.user.username,
                            "timestamp": time.time()
                        }
                    }
                )

            # Leave channel group
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        sig_type = data.get("type", "message")
        payload = data.get("payload", {})
        target = data.get("target", "all")
        display_name = self.user.get_full_name() or self.user.username

        # Sanitize and persist chat messages
        if sig_type == "chat":
            raw_text = str(payload.get("text", "")).strip()
            if not raw_text:
                return
            clean_text = html.escape(raw_text)
            payload["text"] = clean_text
            await self.save_chat_message(self.meeting_id, self.user, display_name, clean_text)

        # Host moderation authorization check
        if sig_type == "host_action":
            is_host = await self.verify_host(self.meeting_id, self.user)
            if not is_host:
                await self.send(text_data=json.dumps({
                    "type": "error",
                    "message": "Unauthorized host action."
                }))
                return

        broadcast_msg = {
            "type": "meeting_broadcast",
            "sender_channel": self.channel_name,
            "target": target,
            "signal": {
                "type": sig_type,
                "sender": self.user.username,
                "sender_name": display_name,
                "payload": payload,
                "target": target,
                "timestamp": time.time()
            }
        }

        await self.channel_layer.group_send(
            self.room_group_name,
            broadcast_msg
        )

    async def meeting_broadcast(self, event):
        # Don't echo back to sender unless targeted specifically
        if event.get("sender_channel") == self.channel_name:
            return

        target = event.get("target", "all")
        if target != "all" and target != self.user.username:
            return

        await self.send(text_data=json.dumps(event["signal"]))

    @database_sync_to_async
    def verify_meeting(self, meeting_id):
        from .models import Meeting
        meeting = Meeting.objects.filter(meeting_id=meeting_id).first()
        if not meeting:
            return False
        if meeting.status in [Meeting.Status.COMPLETED, Meeting.Status.CANCELLED]:
            return False
        return True

    @database_sync_to_async
    def verify_host(self, meeting_id, user):
        from .models import Meeting
        meeting = Meeting.objects.filter(meeting_id=meeting_id).first()
        if not meeting:
            return False
        return meeting.host == user or user.is_superuser

    @database_sync_to_async
    def save_chat_message(self, meeting_id, user, display_name, text):
        from .models import Meeting, MeetingChatMessage
        meeting = Meeting.objects.filter(meeting_id=meeting_id).first()
        if meeting:
            MeetingChatMessage.objects.create(
                meeting=meeting,
                sender=user,
                sender_name=display_name,
                sender_role="Participant",
                message_type=MeetingChatMessage.MessageType.CHAT,
                content=text
            )

    @database_sync_to_async
    def update_presence(self, is_online):
        presence_key = f"hnx_presence_{self.meeting_id}"
        presence = cache.get(presence_key) or {}
        username = self.user.username
        if is_online:
            presence[username] = {
                "username": username,
                "name": self.user.get_full_name() or username,
                "is_host": self.user.is_superuser,
                "last_seen": time.time(),
                "audio_muted": False,
                "video_muted": False
            }
        else:
            presence.pop(username, None)
        cache.set(presence_key, presence, timeout=7200)
