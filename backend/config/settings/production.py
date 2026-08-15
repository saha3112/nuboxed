from .base import *

DEBUG = False
if not SECRET_KEY or SECRET_KEY == "change-me":
    raise RuntimeError("Set a strong SECRET_KEY in the production environment.")
if not ALLOWED_HOSTS:
    raise RuntimeError("Set ALLOWED_HOSTS in the production environment.")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
