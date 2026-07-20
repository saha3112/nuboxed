"""Local fallback settings for running the project without MySQL."""
from .base import *

DEBUG = True
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR.parent / "db.sqlite3",
    }
}
