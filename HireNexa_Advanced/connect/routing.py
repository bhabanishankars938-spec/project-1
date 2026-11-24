from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r"^ws/connect/(?P<meeting_id>[a-zA-Z0-9_-]+)/$", consumers.MeetingSignalConsumer.as_asgi()),
]
