from django.core.management.base import BaseCommand

from apps.catalog.device_presets import seed_device_catalog


class Command(BaseCommand):
    help = "Add the curated phone, tablet and laptop brand/model/variant catalogue."

    def handle(self, *args, **options):
        stats = seed_device_catalog()
        self.stdout.write(self.style.SUCCESS(
            "Device catalogue synced: "
            + ", ".join(f"{key}={value}" for key, value in stats.items())
        ))
