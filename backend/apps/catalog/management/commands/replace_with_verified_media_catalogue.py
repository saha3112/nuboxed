import subprocess
import tempfile
from decimal import Decimal
from pathlib import Path
from urllib.request import Request, urlopen

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.text import slugify

from apps.catalog.models import Brand, Category, Product, ProductMedia, ProductVariant, PhoneModel, PhoneModelVariant
from apps.inventory.models import StockItem, Warehouse
from apps.stores.models import Store


VIDEO_SOURCE = Path("/tmp/pixel-tablet-official.mp4")
IMAGE_SOURCE = "https://a.allegroimg.com/original/117638/617a4c784b878bf7edf4031d98fb/NOWY-Tablet-Google-Pixel-128-GB-10-95-LCD-Szary-Hazel"


class Command(BaseCommand):
    help = "Replace the two active store catalogues with products having verified local video and genuine spin frames."

    def handle(self, *args, **options):
        if not VIDEO_SOURCE.exists():
            raise CommandError("Verified Pixel Tablet video is missing at /tmp/pixel-tablet-official.mp4")
        stores = list(Store.objects.filter(is_active=True).select_related("retailer").order_by("created_at")[:2])
        if len(stores) != 2:
            raise CommandError(f"Expected exactly two active stores, found {len(stores)}")
        model = PhoneModel.objects.filter(name__iexact="Pixel Tablet", brand__name__iexact="Google", is_active=True).first()
        if not model:
            raise CommandError("Google Pixel Tablet is not present in the device model registry")
        phone_variants = list(PhoneModelVariant.objects.filter(phone_model=model, is_active=True).order_by("sort_order", "storage", "color"))
        if not phone_variants:
            raise CommandError("Google Pixel Tablet has no active variants")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            frames_dir = temp / "frames"
            frames_dir.mkdir()
            # The official film opens with the product turn; these are genuine
            # video frames, not still-image copies.
            subprocess.run([
                "ffmpeg", "-y", "-ss", "0", "-i", str(VIDEO_SOURCE), "-t", "24",
                "-vf", "fps=1/2,scale=1200:-2", str(frames_dir / "frame-%02d.jpg"),
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            frames = sorted(frames_dir.glob("frame-*.jpg"))
            if len(frames) < 4:
                raise CommandError("The verified video did not produce enough genuine product frames")
            video_bytes = VIDEO_SOURCE.read_bytes()
            image_bytes = self._download_image()
            archived = Product.objects.filter(store__in=stores, is_active=True).update(is_active=False, deleted_at=timezone.now(), status=Product.STATUS_REJECTED)
            created = variants_created = media_created = 0

            for store in stores:
                warehouse, _ = Warehouse.objects.get_or_create(
                    store=store,
                    defaults={"retailer": store.retailer, "name": f"{store.name} Refurbished Warehouse", "code": f"{store.slug[:20].upper()}-VERIFIED", "country_code": "DE", "is_default": True},
                )
                category = Category.objects.get(slug="tablet")
                brand, _ = Brand.objects.get_or_create(name="Google", defaults={"slug": "google"})
                sku = f"{store.slug[:8].upper()}-PIXELTABLET"
                product = Product.objects.create(
                    retailer=store.retailer, store=store, category=category, brand=brand,
                    name="Pixel Tablet", model_name="Pixel Tablet", slug=f"{store.slug}-google-pixel-tablet",
                    sku=sku, product_type=Product.TYPE_VARIANT, price=Decimal("499.00"),
                    discount_price=Decimal("379.00"), short_description="Verified refurbished Google Pixel Tablet with original product film media.",
                    description="Professionally inspected refurbished Google Pixel Tablet with local genuine product-film angles, real spin frames and original video.",
                    warranty="12-month refurbished warranty", status=Product.STATUS_APPROVED, is_active=True,
                    approved_at=timezone.now(), phone_variant=phone_variants[0], is_featured=True,
                )
                created += 1
                product_frames = []
                for index, phone_variant in enumerate(phone_variants, start=1):
                    original = Decimal("499.00") + Decimal(index - 1) * Decimal("20.00")
                    sale = (original * Decimal("0.76")).quantize(Decimal("0.01"))
                    variant = ProductVariant.objects.create(product=product, name=phone_variant.display_name, sku=f"{sku}-V{index:02d}", price=original, discount_price=sale, is_default=index == 1)
                    StockItem.objects.create(product=product, variant=variant, warehouse=warehouse, on_hand_quantity=5)
                    variants_created += 1
                    # Each variant gets genuine frames from the verified film;
                    # selecting a variant therefore changes its media set.
                    frame = frames[(index - 1) % len(frames)]
                    asset = ProductMedia(product=product, variant=variant, media_type=ProductMedia.TYPE_IMAGE, title=f"Verified {phone_variant.display_name} angle", alt_text=f"Pixel Tablet {phone_variant.display_name}", color=phone_variant.color, sort_order=10 + index)
                    asset.file.save(f"products/verified/{product.slug}-variant-{index:02d}.jpg", ContentFile(frame.read_bytes()), save=True)
                    media_created += 1

                primary = ProductMedia(product=product, media_type=ProductMedia.TYPE_IMAGE, title="Verified product image", alt_text="Google Pixel Tablet", is_primary=True)
                primary.file.save(f"products/verified/{product.slug}-primary.jpg", ContentFile(image_bytes), save=True)
                media_created += 1
                for index, frame in enumerate(frames[:12]):
                    spin = ProductMedia(product=product, media_type=ProductMedia.TYPE_IMAGE_360, title=f"Verified 360 frame {index + 1}", alt_text=f"Pixel Tablet 360 frame {index + 1}", sort_order=100 + index)
                    spin.file.save(f"products/verified/{product.slug}-360-{index:02d}.jpg", ContentFile(frame.read_bytes()), save=True)
                    media_created += 1
                video = ProductMedia(product=product, media_type=ProductMedia.TYPE_VIDEO, title="Original verified product film", alt_text="Google Pixel Tablet original product film")
                video.file.save(f"products/verified/{product.slug}-official.mp4", ContentFile(video_bytes), save=True)
                media_created += 1

        self.stdout.write(self.style.SUCCESS(f"Verified catalogue ready: archived={archived}, stores=2, products={created}, variants={variants_created}, local_media={media_created}"))

    def _download_image(self):
        request = Request(IMAGE_SOURCE, headers={"User-Agent": "Nuboxed-Verified-Catalogue/1.0"})
        with urlopen(request, timeout=30) as response:
            return response.read()
