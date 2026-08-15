from pathlib import Path
import shutil

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Product, ProductMedia


class Command(BaseCommand):
    help = "Import verified Apple iPhone 15 newsroom gallery images and official launch video."

    IMAGE_SOURCES = (
        ("/tmp/iphone15-hero.jpg", "Apple iPhone 15 lineup hero"),
        ("/tmp/iphone15-colors.jpg", "Apple iPhone 15 colour lineup"),
        ("/tmp/iphone15-design.jpg", "Apple iPhone 15 design"),
        ("/tmp/iphone15-camera.jpg", "Apple iPhone 15 camera"),
        ("/tmp/iphone15-usb-c.jpg", "Apple iPhone 15 USB-C"),
    )
    # Public Apple channel replay covering the iPhone 15 launch. The shorter
    # Apple UK promo became private, so it must not be used in the storefront.
    OFFICIAL_VIDEO = "https://www.youtube.com/watch?v=ZiP1l7jlIIA"

    @transaction.atomic
    def handle(self, *args, **options):
        source_files = [(Path(path), title) for path, title in self.IMAGE_SOURCES]
        missing = [str(path) for path, _ in source_files if not path.is_file() or path.stat().st_size < 10_000]
        if missing:
            self.stderr.write("Missing official image files: " + ", ".join(missing))
            return

        products = list(Product.objects.filter(is_active=True, slug__endswith="apple-iphone-15"))
        if not products:
            self.stderr.write("No active Apple iPhone 15 products found.")
            return

        target_dir = Path(settings.MEDIA_ROOT) / "products" / "media" / "products" / "verified"
        target_dir.mkdir(parents=True, exist_ok=True)
        imported = 0

        for product in products:
            # Replace only this product's old/incorrect gallery rows. Do not touch 360 media.
            product.media_items.filter(media_type__in=(ProductMedia.TYPE_IMAGE, ProductMedia.TYPE_VIDEO)).delete()
            prefix = product.slug
            for order, (source, title) in enumerate(source_files):
                filename = f"{prefix}-official-{order + 1}.jpg"
                destination = target_dir / filename
                shutil.copyfile(source, destination)
                ProductMedia.objects.create(
                    product=product,
                    media_type=ProductMedia.TYPE_IMAGE,
                    title=title,
                    alt_text=f"{product.name} — {title}",
                    file=f"products/media/products/verified/{filename}",
                    is_primary=order == 0,
                    sort_order=order,
                )
                imported += 1

            # This is an actual Apple-published video, not a slideshow made from still images.
            ProductMedia.objects.create(
                product=product,
                media_type=ProductMedia.TYPE_VIDEO,
                title="Apple official iPhone 15 launch video",
                alt_text=f"Official Apple video for {product.name}",
                external_url=self.OFFICIAL_VIDEO,
                sort_order=len(source_files),
            )

        self.stdout.write(self.style.SUCCESS(
            f"Imported {imported} official iPhone 15 images and {len(products)} official video links."
        ))
