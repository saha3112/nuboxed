from django.core.management.base import BaseCommand

from apps.catalog.device_presets import rebuild_device_options_and_variants


class Command(BaseCommand):
    help = "Rebuild RAM, storage and colour masters from all device variants."

    def handle(self, *args, **options):
        stats = rebuild_device_options_and_variants()
        self.stdout.write(self.style.SUCCESS(
            "Device options rebuilt: "
            + ", ".join(f"{key}={value}" for key, value in stats.items())
        ))
