import base64
from cryptography.fernet import Fernet
from django.conf import settings

def get_cipher():
    key = getattr(settings, 'ENCRYPTION_KEY', None)
    if not key:
        key = Fernet.generate_key()
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
