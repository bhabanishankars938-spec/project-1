import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.urls import reverse, resolve

try:
    url = reverse("about")
    print("REVERSE SUCCESS:", url)
except Exception as e:
    print("REVERSE ERROR:", e)

from django.test import Client
c = Client()
resp = c.get("/")
print("GET / STATUS:", resp.status_code)
if resp.status_code != 200:
    print("CONTENT PREVIEW:", resp.content[:500])
