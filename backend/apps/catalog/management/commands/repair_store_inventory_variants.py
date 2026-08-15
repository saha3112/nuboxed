from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import (
    AttributeValue,
    Brand,
    PhoneModel,
    Product,
    ProductAttribute,
    ProductVariantAttributeValue,
)
from apps.inventory.models import StockItem, Warehouse


# Consumer-facing configurations, kept deliberately model-specific instead of
# combining arbitrary RAM/storage/colour values across device families.
CONFIGS = {
    "apple-iphone-15": [
        ("", "128GB", "Black"), ("", "128GB", "Blue"), ("", "128GB", "Green"),
        ("", "128GB", "Pink"), ("", "256GB", "Black"), ("", "256GB", "Blue"),
        ("", "256GB", "Green"), ("", "256GB", "Pink"), ("", "512GB", "Black"),
        ("", "512GB", "Blue"), ("", "512GB", "Green"), ("", "512GB", "Pink"),
        ("", "256GB", "Yellow"), ("", "512GB", "Yellow"),
    ],
    "samsung-galaxy-s24": [
        ("8GB", "128GB", "Onyx Black"), ("8GB", "256GB", "Onyx Black"),
        ("8GB", "256GB", "Marble Gray"), ("8GB", "256GB", "Cobalt Violet"),
        ("8GB", "512GB", "Onyx Black"), ("12GB", "512GB", "Onyx Black"),
        ("12GB", "512GB", "Marble Gray"), ("12GB", "512GB", "Cobalt Violet"),
    ],
    "apple-ipad-air-11-inch-m2": [
        ("8GB", "128GB", "Space Gray"), ("8GB", "128GB", "Blue"),
        ("8GB", "256GB", "Space Gray"), ("8GB", "256GB", "Blue"),
        ("8GB", "512GB", "Purple"), ("8GB", "512GB", "Starlight"),
        ("8GB", "1TB", "Purple"), ("8GB", "1TB", "Starlight"),
    ],
    "samsung-galaxy-tab-s9-fe": [
        ("6GB", "128GB", "Gray"), ("6GB", "128GB", "Mint"),
        ("6GB", "128GB", "Silver"), ("8GB", "256GB", "Gray"),
        ("8GB", "256GB", "Mint"), ("8GB", "256GB", "Silver"),
        ("8GB", "256GB", "Lavender"), ("6GB", "256GB", "Gray"),
    ],
    "apple-macbook-air-13-inch-m3": [
        ("8GB", "256GB", "Midnight"), ("8GB", "256GB", "Starlight"),
        ("8GB", "512GB", "Midnight"), ("8GB", "512GB", "Silver"),
        ("16GB", "512GB", "Midnight"), ("16GB", "512GB", "Silver"),
        ("16GB", "1TB", "Midnight"), ("16GB", "1TB", "Starlight"),
    ],
    "dell-xps-13": [
        ("8GB", "256GB", "Platinum"), ("8GB", "512GB", "Platinum"),
        ("16GB", "512GB", "Platinum"), ("16GB", "1TB", "Platinum"),
        ("16GB", "512GB", "Graphite"), ("16GB", "1TB", "Graphite"),
        ("32GB", "1TB", "Platinum"), ("32GB", "1TB", "Graphite"),
    ],
    "google-pixel-tablet": [
        ("8GB", "128GB", "Porcelain"), ("8GB", "128GB", "Hazel"),
        ("8GB", "128GB", "Rose"), ("8GB", "256GB", "Porcelain"),
        ("8GB", "256GB", "Hazel"), ("8GB", "256GB", "Rose"),
        ("8GB", "256GB", "Porcelain"), ("8GB", "128GB", "Hazel"),
    ],
}


class Command(BaseCommand):
    help = "Repair real device variant attributes and make every active store variant available."

    @transaction.atomic
    def handle(self, *args, **options):
        attrs = {
            "ram": ProductAttribute.objects.get_or_create(
                code="ram", defaults={"name": "RAM", "data_type": ProductAttribute.TYPE_SELECT, "is_variant_attribute": True}
            )[0],
            "storage": ProductAttribute.objects.get_or_create(
                code="storage", defaults={"name": "Storage", "data_type": ProductAttribute.TYPE_SELECT, "is_variant_attribute": True}
            )[0],
            "color": ProductAttribute.objects.get_or_create(
                code="color", defaults={"name": "Color", "data_type": ProductAttribute.TYPE_COLOR, "is_variant_attribute": True}
            )[0],
        }
        active = Product.objects.filter(is_active=True).select_related("brand", "store")
        repaired = stock_rows = attribute_rows = 0

        for product in active:
            # Store prefix is variable; the prepared catalogue slug is stable.
            model_key = next((key for key in CONFIGS if product.slug.endswith(key)), None)
            if not model_key:
                continue

            model_name = {
                "apple-iphone-15": "iPhone 15",
                "samsung-galaxy-s24": "Galaxy S24",
                "apple-ipad-air-11-inch-m2": "iPad Air 11-inch (M2)",
                "samsung-galaxy-tab-s9-fe": "Galaxy Tab S9 FE",
                "apple-macbook-air-13-inch-m3": "MacBook Air 13-inch (M3)",
                "dell-xps-13": "XPS 13",
                "google-pixel-tablet": "Pixel Tablet",
            }[model_key]
            phone_model = PhoneModel.objects.filter(name__iexact=model_name, is_active=True).first()
            if phone_model:
                product.phone_variant = phone_model.variants.filter(is_active=True).order_by("sort_order").first()
                product.save(update_fields=["phone_variant", "updated_at"])

            variants = list(product.variants.order_by("created_at", "id"))
            configs = CONFIGS[model_key]
            if len(variants) != len(configs):
                raise RuntimeError(f"{product.slug}: expected {len(configs)} variants, found {len(variants)}")

            warehouse = Warehouse.objects.filter(store=product.store, is_default=True).first() or Warehouse.objects.filter(store=product.store).first()
            if not warehouse:
                raise RuntimeError(f"No warehouse found for {product.store.name}")

            for index, (variant, config) in enumerate(zip(variants, configs), start=1):
                ram, storage, color = config
                variant.name = " / ".join(value for value in config if value)
                variant.is_default = index == 1
                variant.deleted_at = None
                variant.save(update_fields=["name", "is_default", "deleted_at", "updated_at"])
                ProductVariantAttributeValue.objects.filter(variant=variant).delete()
                for code, value in (("ram", ram), ("storage", storage), ("color", color)):
                    if not value:
                        continue
                    attr = attrs[code]
                    av, _ = AttributeValue.objects.get_or_create(attribute=attr, value=value, defaults={"label": value})
                    ProductVariantAttributeValue.objects.create(variant=variant, attribute=attr, value=value)
                    attribute_rows += 1

                stock, _ = StockItem.objects.get_or_create(product=product, variant=variant, warehouse=warehouse)
                stock.on_hand_quantity = max(stock.on_hand_quantity, 10)
                stock.reserved_quantity = min(stock.reserved_quantity, stock.on_hand_quantity)
                stock.damaged_quantity = 0
                stock.save(update_fields=["on_hand_quantity", "reserved_quantity", "damaged_quantity", "updated_at"])
                stock_rows += 1
            repaired += 1

        self.stdout.write(self.style.SUCCESS(
            f"Inventory repaired: products={repaired}, variants_stocked={stock_rows}, attribute_values={attribute_rows}"
        ))
