import base64
import hashlib
from cryptography.fernet import Fernet
from django.conf import settings

def get_cipher():
    key = getattr(settings, 'ENCRYPTION_KEY', None)
    if not key:
        # Derive a stable Fernet key from SECRET_KEY so encrypted marketplace
        # credentials remain readable after process restarts. Production may
        # still override this with a dedicated ENCRYPTION_KEY environment var.
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
        settings.ENCRYPTION_KEY = key
    return Fernet(key)

def encrypt(text: str) -> str:
    if not text:
        return text
    return get_cipher().encrypt(text.encode()).decode()

def decrypt(token: str) -> str:
    if not token:
        return token
    try:
        return get_cipher().decrypt(token.encode()).decode()
    except Exception:
        return token
