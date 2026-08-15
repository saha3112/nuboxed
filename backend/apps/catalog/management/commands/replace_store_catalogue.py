from django.core.management.base import BaseCommand

from apps.catalog.store_seed import replace_store_catalogue


class Command(BaseCommand):
    help = "Archive demo products from the two active stores and seed the refurbished device catalogue."

    def handle(self, *args, **options):
        stats = replace_store_catalogue()
        self.stdout.write(self.style.SUCCESS("Store catalogue replaced: " + ", ".join(f"{key}={value}" for key, value in stats.items())))
