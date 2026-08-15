from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Product, ProductMedia


DEVICE_SLUGS = (
    "apple-iphone-15",
    "samsung-galaxy-s24",
    "apple-ipad-air-11-inch-m2",
    "samsung-galaxy-tab-s9-fe",
    "apple-macbook-air-13-inch-m3",
    "dell-xps-13",
)


class Command(BaseCommand):
    help = "Add the local refurbished smartphone, tablet and laptop catalogue to both active stores."

    @transaction.atomic
    def handle(self, *args, **options):
        stores = list(Product.objects.filter(is_active=True).values_list("store_id", flat=True).distinct())
        if len(stores) != 2:
            raise RuntimeError(f"Expected two active-store IDs, found {len(stores)}")

        products = list(Product.objects.filter(
            store_id__in=stores,
            slug__in=[f"{prefix}-{base}" for prefix in ("abc-store", "xyz-store") for base in DEVICE_SLUGS],
        ))
        if len(products) != 12:
            raise RuntimeError(f"Expected 12 prepared device products, found {len(products)}")

        activated = media_added = videos_added = 0
        for product in products:
            product.is_active = True
            product.deleted_at = None
            product.status = Product.STATUS_APPROVED
            product.approved_at = product.approved_at or timezone.now()
            product.save(update_fields=["is_active", "deleted_at", "status", "approved_at", "updated_at"])
            activated += 1

            # Keep the current gallery policy: angles are normal local images;
            # do not expose the old synthetic 360 media type.
            product.media_items.filter(media_type=ProductMedia.TYPE_IMAGE_360).delete()
            for index in range(8):
                matches = [
                    f"products/media/products/materialized/{product.slug}-360-{index:02d}{extension}"
                    for extension in (".jpg", ".png")
                ]
                relative = next((name for name in matches if default_storage.exists(name)), None)
                if not relative or ProductMedia.objects.filter(product=product, file=relative).exists():
                    continue
                media = ProductMedia(
                    product=product,
                    media_type=ProductMedia.TYPE_IMAGE,
                    title=f"Official product angle {index + 1}",
                    alt_text=f"{product.name} product angle {index + 1}",
                    sort_order=20 + index,
                )
                media.file.name = relative
                media.save()
                media_added += 1

            video = f"products/media/products/materialized/{product.slug}-showcase.mp4"
            if default_storage.exists(video) and not product.media_items.filter(media_type=ProductMedia.TYPE_VIDEO, file=video).exists():
                media = ProductMedia(
                    product=product,
                    media_type=ProductMedia.TYPE_VIDEO,
                    title="Official product showcase video",
                    alt_text=f"{product.name} official product showcase",
                    sort_order=10,
                )
                media.file.name = video
                media.save()
                videos_added += 1

        self.stdout.write(self.style.SUCCESS(
            f"Device catalogue ready: stores=2, products_activated={activated}, "
            f"local_angles_added={media_added}, local_videos_added={videos_added}"
        ))
