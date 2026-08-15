from django.core.management.base import BaseCommand

from apps.catalog.device_presets import backfill_device_model_years


class Command(BaseCommand):
    help = "Fill missing release years for all device models using generation-aware rules."

    def handle(self, *args, **options):
        stats = backfill_device_model_years()
        self.stdout.write(self.style.SUCCESS(
            "Device model years updated: "
            + ", ".join(f"{key}={value}" for key, value in stats.items())
        ))
