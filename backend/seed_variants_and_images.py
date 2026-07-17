import os
import django
from django.core.files.base import ContentFile
import urllib.request

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from apps.catalog.models import (
    Product, ProductVariant, ProductMedia, 
    ProductAttribute, ProductAttributeOption, ProductVariantAttributeValue
)
from apps.stores.models import Store
from django.db import transaction

def download_image(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req)
        return response.read()
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return None

@transaction.atomic
def seed():
    print("Seeding variants and images...")
    
    # 1. Setup Attributes (Color)
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
    for name, value in colors:
        opt, _ = ProductAttributeOption.objects.get_or_create(
            attribute=color_attr,
            value=name
        )
        color_options[name] = opt

    # 2. Add Dummy Images to Products
    placeholder_img = download_image("https://placehold.co/600x600/e2e8f0/475569.png?text=Product+Image")
    
    products = Product.objects.all()
    for product in products:
        if not product.media_items.exists() and placeholder_img:
            media = ProductMedia(product=product)
            media.file.save(f"product_{product.id}.png", ContentFile(placeholder_img), save=True)
            print(f"Added image to {product.name}")
        
        # 3. Add Variants
        if not product.variants.exists():
            for color_name in ["Black", "White"]:
                variant = ProductVariant.objects.create(
                    product=product,
                    sku=f"{product.sku}-{color_name[:3].upper()}",
                    price=product.price,
                    discount_price=product.discount_price,
                    inventory_quantity=10,
                )
                ProductVariantAttributeValue.objects.create(
                    variant=variant,
                    attribute=color_attr,
                    option=color_options[color_name]
                )
            print(f"Added variants to {product.name}")

    # 4. Add logo/banner to Test Store
    store = Store.objects.filter(slug="test-store").first()
    if store and not store.logo:
        logo_img = download_image("https://placehold.co/400x400/3b82f6/ffffff.png?text=Test+Store")
        if logo_img:
            store.logo.save("test_store_logo.png", ContentFile(logo_img), save=True)
            
            
    print("Done!")

if __name__ == "__main__":
    seed()
