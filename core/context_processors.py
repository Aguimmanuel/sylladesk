from django.conf import settings

BRAND_NAME = "SyllaDesk"


def brand(request):
    # "Forgot password?" link shows only when a real email sender is configured
    return {"BRAND_NAME": BRAND_NAME,
            "email_configured": bool(getattr(settings, "EMAIL_HOST_USER", ""))}
