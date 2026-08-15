import json
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.device_presets import rebuild_device_options_and_variants, sync_catalog_payload


class Command(BaseCommand):
    help = "Merge a JSON phone/tablet/laptop catalogue feed without deleting existing data."

    def add_arguments(self, parser):
        parser.add_argument("--url", default="", help="JSON feed URL; defaults to DEVICE_CATALOG_FEED_URL")

    def handle(self, *args, **options):
        feed_url = (options.get("url") or getattr(settings, "DEVICE_CATALOG_FEED_URL", "")).strip()
        if not feed_url:
            raise CommandError("Set DEVICE_CATALOG_FEED_URL or pass --url")
        try:
            request = Request(feed_url, headers={"User-Agent": "Nuboxed-Device-Catalog/1.0"})
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise CommandError(f"Could not read device feed: {exc}")
        stats = sync_catalog_payload(payload)
        stats.update(rebuild_device_options_and_variants())
        self.stdout.write(self.style.SUCCESS("Device feed merged: " + ", ".join(f"{key}={value}" for key, value in stats.items())))
