from io import BytesIO

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from PIL import Image, ImageChops, ImageStat

from apps.catalog.models import Product, ProductMedia


class Command(BaseCommand):
    help = "Crop excessive empty canvas around active product images for consistent gallery framing."

    def handle(self, *args, **options):
        changed = skipped = 0
        for media in ProductMedia.objects.filter(
            product__is_active=True,
            media_type=ProductMedia.TYPE_IMAGE,
        ).exclude(file=""):
            if not media.file:
                skipped += 1
                continue
            try:
                media.file.open("rb")
                original = Image.open(BytesIO(media.file.read()))
                media.file.close()
                image = original.convert("RGBA")
                rgb = image.convert("RGB")
                corner = rgb.crop((0, 0, min(24, rgb.width), min(24, rgb.height)))
                background = Image.new("RGB", rgb.size, tuple(int(value) for value in ImageStat.Stat(corner).mean))
                mask = ImageChops.difference(rgb, background).convert("L").point(
                    lambda value: 255 if value > 12 else 0
                )
                bbox = mask.getbbox()
                if not bbox:
                    skipped += 1
                    continue

                left, top, right, bottom = bbox
                width, height = right - left, bottom - top
                # Keep a breathing margin around the device, but remove the
                # large empty canvas that makes the product look tiny.
                pad_x = max(12, int(width * 0.22))
                pad_y = max(12, int(height * 0.22))
                crop = (
                    max(0, left - pad_x),
                    max(0, top - pad_y),
                    min(image.width, right + pad_x),
                    min(image.height, bottom + pad_y),
                )
                if crop == (0, 0, image.width, image.height):
                    skipped += 1
                    continue

                cropped = image.crop(crop)
                output = BytesIO()
                extension = (media.file.name.rsplit(".", 1)[-1] or "jpg").lower()
                if extension in {"jpg", "jpeg"}:
                    cropped.convert("RGB").save(output, format="JPEG", quality=94, optimize=True)
                else:
                    cropped.save(output, format="PNG", optimize=True)
                output.seek(0)
                with default_storage.open(media.file.name, "wb") as destination:
                    destination.write(output.read())
                changed += 1
            except Exception as exc:
                skipped += 1
                self.stderr.write(f"Could not normalize {media.file.name}: {exc}")

        self.stdout.write(self.style.SUCCESS(f"Product image framing normalized: changed={changed}, skipped={skipped}"))
