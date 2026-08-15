import mimetypes
import subprocess
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.catalog.models import Product, ProductMedia


class Command(BaseCommand):
    help = "Download active store images locally and build local 360 frames/showcase videos."

    def handle(self, *args, **options):
        media_root = Path("media/products/materialized")
        media_root.mkdir(parents=True, exist_ok=True)
        stats = {"products": 0, "images": 0, "frames": 0, "videos": 0, "failed": 0}

        for product in Product.objects.filter(is_active=True).prefetch_related("media_items"):
            image = product.media_items.filter(media_type=ProductMedia.TYPE_IMAGE).first()
            if not image or (not image.external_url and not image.file):
                continue
            try:
                if image.file:
                    image.file.open("rb")
                    payload = image.file.read()
                    image.file.close()
                    extension = Path(image.file.name).suffix or ".jpg"
                else:
                    request = Request(image.external_url, headers={"User-Agent": "Nuboxed-Media/1.0"})
                    with urlopen(request, timeout=30) as response:
                        payload = response.read()
                        content_type = response.headers.get_content_type()
                    extension = mimetypes.guess_extension(content_type) or ".jpg"
                if extension == ".jpe":
                    extension = ".jpg"
                stem = slugify(product.slug)
                if not image.file:
                    image.file.save(f"products/materialized/{stem}{extension}", ContentFile(payload), save=True)
                image.external_url = ""
                image.save(update_fields=["external_url", "updated_at"])
                stats["images"] += 1

                stats["products"] += 1
            except Exception as exc:
                stats["failed"] += 1
                self.stderr.write(f"Could not materialize {product.slug}: {exc}")

        self.stdout.write(self.style.SUCCESS("Local product media ready: " + ", ".join(f"{key}={value}" for key, value in stats.items())))
