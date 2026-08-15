from pathlib import Path
import hashlib
import shutil

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Product, ProductMedia


class Command(BaseCommand):
    help = "Add distinct manufacturer-sourced gallery images without creating synthetic media."

    SOURCES = {
        "apple-ipad-air-11-inch-m2": (
            ("/tmp/catalog-ipad-hero", "Apple iPad Air M2 hero"),
            ("/tmp/catalog-ipad-lineup", "Apple iPad Air M2 lineup"),
            ("/tmp/catalog-ipad-colors", "Apple iPad Air M2 colours"),
            ("/tmp/catalog-ipad-camera", "Apple iPad Air M2 camera"),
        ),
        "apple-macbook-air-13-inch-m3": (
            ("/tmp/catalog-mac-hero", "Apple MacBook Air M3 hero"),
            ("/tmp/catalog-mac-lifestyle", "Apple MacBook Air M3 lifestyle"),
            ("/tmp/catalog-mac-front", "Apple MacBook Air M3 front"),
            ("/tmp/catalog-mac-keyboard", "Apple MacBook Air M3 keyboard"),
        ),
        "samsung-galaxy-s24": (
            ("/tmp/catalog-s24-share", "Samsung Galaxy S24 official product"),
            ("/tmp/catalog-s24-thumb", "Samsung Galaxy S24 product detail"),
            ("/tmp/catalog-s24-highlights", "Samsung Galaxy S24 official highlights"),
            ("/tmp/catalog-s24-translate", "Samsung Galaxy S24 feature view"),
        ),
        "samsung-galaxy-tab-s9-fe": (
            ("/tmp/catalog-tab-thumb", "Samsung Galaxy Tab S9 FE official product"),
        ),
        "dell-xps-13": (
            ("/tmp/catalog-dell-thumb", "Dell XPS 13 official product"),
            ("/tmp/catalog-dell-ai", "Dell XPS 13 official feature view"),
        ),
    }

    @transaction.atomic
    def handle(self, *args, **options):
        target_dir = Path(settings.MEDIA_ROOT) / "products" / "media" / "products" / "verified"
        target_dir.mkdir(parents=True, exist_ok=True)
        added = skipped = missing = 0

        for model_slug, sources in self.SOURCES.items():
            products = Product.objects.filter(is_active=True, slug__endswith=model_slug)
            for product in products:
                existing_hashes = set()
                for media in product.media_items.filter(media_type=ProductMedia.TYPE_IMAGE):
                    if media.file:
                        with media.file.open("rb") as stream:
                            existing_hashes.add(hashlib.sha256(stream.read()).hexdigest())

                order = product.media_items.filter(media_type=ProductMedia.TYPE_IMAGE).count()
                for source_name, title in sources:
                    source = Path(source_name)
                    if not source.is_file() or source.stat().st_size < 10_000:
                        missing += 1
                        continue
                    with source.open("rb") as stream:
                        payload = stream.read()
                    digest = hashlib.sha256(payload).hexdigest()
                    if digest in existing_hashes:
                        skipped += 1
                        continue
                    filename = f"{product.slug}-official-gallery-{order + 1}{source.suffix.lower() or '.jpg'}"
                    destination = target_dir / filename
                    shutil.copyfile(source, destination)
                    ProductMedia.objects.create(
                        product=product,
                        media_type=ProductMedia.TYPE_IMAGE,
                        title=title,
                        alt_text=f"{product.name} — {title}",
                        file=f"products/media/products/verified/{filename}",
                        is_primary=False,
                        sort_order=order,
                    )
                    existing_hashes.add(digest)
                    order += 1
                    added += 1

        self.stdout.write(self.style.SUCCESS(
            f"Official catalogue images imported: added={added}, duplicate_images_skipped={skipped}, missing={missing}. "
            "No videos were generated from still images."
        ))
