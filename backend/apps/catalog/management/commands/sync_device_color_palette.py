from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import AttributeValue, PhoneColorOption, PhoneModelVariant, ProductAttribute


# Representative display swatches for the manufacturer's named finishes.
# These are used consistently by admin, listings, quick views and detail pages.
COLOR_HEX = {
    "Black": "#111111",
    "Blue": "#2f5fae",
    "Cobalt Violet": "#75639b",
    "Graphite": "#45484d",
    "Gray": "#7a7f86",
    "Hazel": "#928b7d",
    "Lavender": "#b8a8c9",
    "Marble Gray": "#9b9da1",
    "Midnight": "#1f2a36",
    "Mint": "#b7d4c2",
    "Onyx Black": "#1b1b1d",
    "Pink": "#e8a7b9",
    "Platinum": "#d5d8dc",
    "Porcelain": "#f1eee4",
    "Purple": "#8064a2",
    "Rose": "#d99aaa",
    "Silver": "#c5c9cf",
    "Space Gray": "#686d73",
    "Starlight": "#eee2c9",
    "Yellow": "#e3bd32",
    "Green": "#548766",
    "Red": "#b9473d",
}


class Command(BaseCommand):
    help = "Synchronize actual device finish names and color swatches across admin and storefront data."

    @transaction.atomic
    def handle(self, *args, **options):
        color_attr, _ = ProductAttribute.objects.get_or_create(
            code="color",
            defaults={
                "name": "Color",
                "data_type": ProductAttribute.TYPE_COLOR,
                "is_variant_attribute": True,
            },
        )
        attribute_count = phone_option_count = model_variant_count = 0
        for name, hex_value in COLOR_HEX.items():
            value, created = AttributeValue.objects.get_or_create(
                attribute=color_attr,
                value=name,
                defaults={"label": name, "hex_color": hex_value},
            )
            if value.label != name or value.hex_color != hex_value:
                value.label = name
                value.hex_color = hex_value
                value.save(update_fields=["label", "hex_color", "updated_at"])
            attribute_count += 1

            option, created = PhoneColorOption.objects.get_or_create(
                name=name,
                defaults={"color_hex": hex_value, "sort_order": attribute_count},
            )
            if option.color_hex != hex_value or option.sort_order != attribute_count:
                option.color_hex = hex_value
                option.sort_order = attribute_count
                option.save(update_fields=["color_hex", "sort_order", "updated_at"])
            phone_option_count += 1

            updated = PhoneModelVariant.objects.filter(color__iexact=name).update(color_hex=hex_value)
            model_variant_count += updated

        self.stdout.write(self.style.SUCCESS(
            f"Color palette synchronized: attribute_values={attribute_count}, "
            f"admin_options={phone_option_count}, model_variants_updated={model_variant_count}"
        ))
