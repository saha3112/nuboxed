import hashlib

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Product, ProductMedia


class Command(BaseCommand):
    help = "Remove duplicate angle images and non-original still-image videos from active products."

    @transaction.atomic
    def handle(self, *args, **options):
        duplicate_images = removed_videos = 0
        for product in Product.objects.filter(is_active=True).prefetch_related("media_items"):
            seen_hashes = set()
            images = list(product.media_items.filter(media_type=ProductMedia.TYPE_IMAGE).order_by("-is_primary", "sort_order", "created_at"))
            for media in images:
                if not media.file:
                    continue
                with media.file.open("rb") as source:
                    digest = hashlib.sha256(source.read()).hexdigest()
                if digest in seen_hashes:
                    media.delete()
                    duplicate_images += 1
                else:
                    seen_hashes.add(digest)

            for media in list(product.media_items.filter(media_type=ProductMedia.TYPE_VIDEO)):
                # Only verified local footage is allowed. Materialized
                # four-second files were generated from still product images.
                if media.file and "verified/" not in media.file.name:
                    media.delete()
                    removed_videos += 1

        remaining = {
            "images": ProductMedia.objects.filter(product__is_active=True, media_type=ProductMedia.TYPE_IMAGE).count(),
            "videos": ProductMedia.objects.filter(product__is_active=True, media_type=ProductMedia.TYPE_VIDEO).count(),
        }
        self.stdout.write(self.style.SUCCESS(
            f"Product media sanitized: duplicate_images_removed={duplicate_images}, "
            f"non_original_videos_removed={removed_videos}, remaining={remaining}"
        ))
