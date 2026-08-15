from .base import *

DEBUG = True
# The local portal is commonly run without a Celery worker. Keep marketplace
# actions realtime in this development profile; production settings continue
# to use the normal Celery worker/beat queue.
CELERY_TASK_ALWAYS_EAGER = True
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("DB_NAME", "nuboxed"),
        "USER": os.getenv("DB_USER", "root"),
        "PASSWORD": os.getenv("DB_PASSWORD", "Chandan.1"),
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("DB_PORT", "3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
            "collation": "utf8mb4_general_ci",
            "init_command": "SET NAMES utf8mb4 COLLATE utf8mb4_general_ci",
        },
        # Reuse the MySQL connection between requests; this removes the
        # connection handshake from every storefront/admin page load.
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}

if os.getenv("DB_SOCKET"):
    DATABASES["default"]["OPTIONS"]["unix_socket"] = os.getenv("DB_SOCKET")
