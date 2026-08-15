import hashlib

from django.core.management.base import BaseCommand

from apps.catalog.models import Product, ProductMedia


class Command(BaseCommand):
    help = "Remove synthetic duplicate gallery/360/video assets and retain only genuine distinct media."

    def handle(self, *args, **options):
        removed = {"duplicate_images": 0, "fake_360": 0, "fake_videos": 0}

        for product in Product.objects.filter(is_active=True).prefetch_related("media_items"):
            seen_images = set()
            image_items = list(product.media_items.filter(media_type=ProductMedia.TYPE_IMAGE).order_by("sort_order", "created_at"))
            for item in image_items:
                try:
                    if item.file:
                        item.file.open("rb")
                        digest = hashlib.sha256(item.file.read()).hexdigest()
                        item.file.close()
                    else:
                        digest = hashlib.sha256((item.external_url or "").encode()).hexdigest()
                except (ValueError, OSError):
                    digest = item.external_url or str(item.pk)
                if digest in seen_images:
                    if item.file:
                        item.file.delete(save=False)
                    item.delete()
                    removed["duplicate_images"] += 1
                else:
                    seen_images.add(digest)

            # A generated showcase from one still image is not a product video.
            for item in product.media_items.filter(media_type=ProductMedia.TYPE_VIDEO):
                if item.title == "Local product showcase" or "showcase" in (item.file.name if item.file else "").lower():
                    if item.file:
                        item.file.delete(save=False)
                    item.delete()
                    removed["fake_videos"] += 1

            # Keep 360 only when at least two distinct local frames exist.
            spin_items = list(product.media_items.filter(media_type=ProductMedia.TYPE_IMAGE_360).order_by("sort_order", "created_at"))
            frame_hashes = set()
            for item in spin_items:
                try:
                    if item.file:
                        item.file.open("rb")
                        digest = hashlib.sha256(item.file.read()).hexdigest()
                        item.file.close()
                    else:
                        digest = hashlib.sha256((item.external_url or "").encode()).hexdigest()
                except (ValueError, OSError):
                    digest = item.external_url or str(item.pk)
                frame_hashes.add(digest)
            if len(frame_hashes) < 2:
                for item in spin_items:
                    if item.file:
                        item.file.delete(save=False)
                    item.delete()
                    removed["fake_360"] += 1

        self.stdout.write(self.style.SUCCESS("Product media cleaned: " + ", ".join(f"{key}={value}" for key, value in removed.items())))
