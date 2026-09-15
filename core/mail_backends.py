"""Mail via the owner's Google Apps Script Web App (V2-13, zero-naira route).

Render's FREE tier blocks outbound SMTP ports (25/465/587) entirely, but
HTTPS on 443 is always open. This backend POSTs JSON to an Apps Script Web
App which calls MailApp.sendEmail() from the owner's Gmail.

Render env (never in git/chat):
  APPS_SCRIPT_MAIL_URL    the .../exec URL of the deployed Web App
  APPS_SCRIPT_MAIL_TOKEN  long random string, MUST match the script's SHARED_TOKEN

The script must answer {"ok": true} - anything else raises OSError so the
loud password-reset path tells the student the truth instead of lying.
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
            raise  # network/timeout errors keep their meaning for the caller
        if '"ok":true' not in body.replace(" ", ""):
            raise OSError(f"Apps Script mailer did not confirm success: {body[:200]}")
        return True
