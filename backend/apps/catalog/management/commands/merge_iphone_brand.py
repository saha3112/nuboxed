from django.core.management.base import BaseCommand

from apps.catalog.device_presets import merge_iphone_brand_into_apple


class Command(BaseCommand):
    help = "Merge the legacy iPhone device brand into Apple without losing linked products."

    def handle(self, *args, **options):
        stats = merge_iphone_brand_into_apple()
        self.stdout.write(self.style.SUCCESS("iPhone brand merged into Apple: " + ", ".join(f"{k}={v}" for k, v in stats.items())))
