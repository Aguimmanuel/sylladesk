"""Sends mail through a Google Apps Script Web App.

Render's free tier blocks outbound SMTP, so mail goes out over HTTPS
instead: a JSON POST to the Web App, which relays via Gmail.

Requires APPS_SCRIPT_MAIL_URL and APPS_SCRIPT_MAIL_TOKEN. The script must
reply {"ok": true}; anything else raises OSError so callers treat the
send as failed.
"""
import json
import urllib.request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class AppsScriptMailBackend(BaseEmailBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.url = getattr(settings, "APPS_SCRIPT_MAIL_URL", "")
        self.token = getattr(settings, "APPS_SCRIPT_MAIL_TOKEN", "")

    def send_messages(self, email_messages):
        if not self.url or not self.token:
            raise OSError("Apps Script mail is not configured (URL/token missing)")
        sent = 0
        for message in email_messages:
            self._post(
                to=", ".join(message.recipients()),
                subject=message.subject,
                text=message.body,
            )
            sent += 1
        return sent

    def _post(self, *, to, subject, text):
        payload = json.dumps(
            {"to": to, "subject": subject, "text": text, "token": self.token}
        ).encode("utf-8")
        req = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", "replace")
        except OSError:
            raise
        if '"ok":true' not in body.replace(" ", ""):
            raise OSError(f"Apps Script mailer did not confirm success: {body[:200]}")
        return True
