from django.conf import settings

BRAND_NAME = "SyllaDesk"


def brand(request):
    # "Forgot password?" link shows only when a real email sender is configured
    apps_script_ready = bool(getattr(settings, "APPS_SCRIPT_MAIL_URL", "")
                              and getattr(settings, "APPS_SCRIPT_MAIL_TOKEN", ""))
    return {"BRAND_NAME": BRAND_NAME,
            "email_configured": bool(getattr(settings, "EMAIL_HOST_USER", "")) or apps_script_ready}
