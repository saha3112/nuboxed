from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Product, ProductMedia


class Command(BaseCommand):
    help = "Add only public manufacturer-published product videos; never create videos from still images."

    VIDEOS = {
        "samsung-galaxy-tab-s9-fe": (
            "https://www.youtube.com/watch?v=ys0ZHJmFF2k",
            "Samsung Galaxy Tab S9 FE official unboxing",
        ),
    }

    @transaction.atomic
    def handle(self, *args, **options):
        added = skipped = 0
        for model_slug, (url, title) in self.VIDEOS.items():
            for product in Product.objects.filter(is_active=True, slug__endswith=model_slug):
                if product.media_items.filter(media_type=ProductMedia.TYPE_VIDEO, external_url=url).exists():
                    skipped += 1
                    continue
                ProductMedia.objects.create(
                    product=product,
                    media_type=ProductMedia.TYPE_VIDEO,
                    title=title,
                    alt_text=f"{product.name} — {title}",
                    external_url=url,
                    sort_order=product.media_items.filter(media_type=ProductMedia.TYPE_IMAGE).count() + 1,
                )
                added += 1
        self.stdout.write(self.style.SUCCESS(
            f"Verified product videos imported: added={added}, already_present={skipped}. "
            "No still-image videos created."
        ))
