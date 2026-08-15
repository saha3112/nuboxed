import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from apps.common.encryption import decrypt
from apps.settings_app.models import Setting


DEFAULTS = {
    "enabled": False,
    "provider": "turnstile",
    "alignment": "left",
    "site_key": "",
    "secret_key": "",
    "protect_customer_login": True,
    "protect_customer_register": True,
    "protect_retailer_login": True,
    "protect_admin_login": True,
    "protect_public_forms": True,
}

VERIFY_ENDPOINTS = {
    "recaptcha": "https://www.google.com/recaptcha/api/siteverify",
    "hcaptcha": "https://hcaptcha.com/siteverify",
    "turnstile": "https://challenges.cloudflare.com/turnstile/v0/siteverify",
}


def get_captcha_settings():
    values = dict(DEFAULTS)
    setting = Setting.objects.filter(key="captcha_settings", is_active=True).first()
    if setting and isinstance(setting.value, dict):
        values.update(setting.value)
    if values.get("secret_key"):
        values["secret_key"] = decrypt(values["secret_key"])
    return values


def public_captcha_settings(scope):
    values = get_captcha_settings()
    enabled = bool(values.get("enabled") and values.get("site_key") and values.get("secret_key") and values.get(f"protect_{scope}"))
    return {"enabled": enabled, "provider": values.get("provider", "turnstile"), "site_key": values.get("site_key", "") if enabled else "", "alignment": values.get("alignment", "left")}


def verify_captcha(request, scope, enabled_override=None):
    values = get_captcha_settings()
    if enabled_override is False or not (values.get("enabled") and values.get(f"protect_{scope}")):
        return True, ""
    provider = values.get("provider", "turnstile")
    secret = values.get("secret_key", "")
    token_names = {"recaptcha": "g-recaptcha-response", "hcaptcha": "h-captcha-response", "turnstile": "cf-turnstile-response"}
    token = request.POST.get(token_names.get(provider, ""), "").strip()
    if not secret or not token:
        return False, "Please complete the security check."
    payload = urlencode({"secret": secret, "response": token, "remoteip": request.META.get("REMOTE_ADDR", "")}).encode()
    try:
        response = urlopen(Request(VERIFY_ENDPOINTS[provider], data=payload, method="POST"), timeout=8)
        result = json.loads(response.read().decode("utf-8"))
    except Exception:
        return False, "Captcha verification is temporarily unavailable. Please try again."
    if result.get("success") is True:
        return True, ""
    return False, "Security verification failed. Please try again."
