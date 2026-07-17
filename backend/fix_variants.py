import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from apps.catalog.models import (
    Product, ProductVariant, ProductAttribute, 
    ProductAttributeOption, ProductVariantAttributeValue
)
from django.db import transaction

@transaction.atomic
def fix_variants():
    # 1. Ensure Color Attribute exists
    color_attr, _ = ProductAttribute.objects.get_or_create(
        name="Color", defaults={"code": "color", "data_type": "select", "is_variant_attribute": True}
    )
    
    colors = [
        ("Black", "#000000"),
        ("White", "#FFFFFF"),
        ("Red", "#FF0000"),
        ("Blue", "#0000FF"),
        ("Green", "#008000")
    ]
    
    color_options = {}
    for name, _ in colors:
        opt, _ = ProductAttributeOption.objects.get_or_create(
            attribute=color_attr,
            value=name
        )
        color_options[name] = opt

    # 2. Update existing variants
    variants = ProductVariant.objects.all()
    for variant in variants:
        if not variant.attribute_values.filter(attribute=color_attr).exists():
            # Extract color from name if possible, or just assign random
            assigned_color = "Black"
            if "White" in variant.sku or "WHI" in variant.sku:
                assigned_color = "White"
            elif "Red" in variant.sku or "RED" in variant.sku:
                assigned_color = "Red"
            
            ProductVariantAttributeValue.objects.create(
                variant=variant,
                attribute=color_attr,
                option=color_options[assigned_color]
            )

    # 3. Create missing variants for products that have none
    products = Product.objects.all()
    for product in products:
        if not product.variants.exists():
            for color_name in ["Black", "White", "Blue"]:
                variant = ProductVariant.objects.create(
                    product=product,
                    name=f"{product.name} - {color_name}",
                    sku=f"{product.sku}-{color_name[:3].upper()}",
                    price=product.price,
                    discount_price=product.discount_price,
                )
                ProductVariantAttributeValue.objects.create(
                    variant=variant,
                    attribute=color_attr,
                    option=color_options[color_name]
                )
    print(f"Total variants: {ProductVariant.objects.count()} and {ProductVariantAttributeValue.objects.count()} attribute links.")

if __name__ == "__main__":
    fix_variants()
