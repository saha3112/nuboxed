"""Passenger entrypoint for cPanel Python applications."""

import os
import sys

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Passenger may start the application from a directory other than the project
# root, so load the cPanel environment file using an absolute project path.
load_dotenv(os.path.join(BASE_DIR, ".env"))
# Passenger is the production entrypoint even if a copied .env still contains
# a development settings value.
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.production"

from config.wsgi import application  # noqa: E402
