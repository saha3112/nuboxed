"""Project-root Passenger entrypoint for cPanel deployments."""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv

# cPanel deployments normally keep .env in the project root. For the existing
# local layout, fall back to backend/.env so the configured database settings
# continue to be used without requiring a second environment file.
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(BACKEND_ROOT / ".env")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

from config.wsgi import application  # noqa: E402
