from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.catalog.models import Brand, Category, Product, ProductMedia, ProductVariant, PhoneModelVariant
from apps.inventory.models import StockItem, Warehouse
from apps.stores.models import Store


# Official manufacturer image/product pages are kept as external references so
# the demo catalogue does not ship copied binaries into the repository.
STORE_CATALOGUE = [
    {
        "model": "iPhone 15", "brand": "Apple", "category": "Smartphones", "price": "799.00",
        "image": "https://store.storeimages.cdn-apple.com/4982/as-images.apple.com/is/iphone-15-finish-select-202309-6-1inch-blue?wid=800&hei=1000&fmt=jpeg&qlt=90&.v=1692923777972",
        "product_page": "https://www.apple.com/iphone-15/",
    },
    {
        "model": "Galaxy S24", "brand": "Samsung", "category": "Smartphones", "price": "699.00",
        "image": "https://images.samsung.com/is/image/samsung/p6pim/uk/sm-s921bzydeub/gallery/uk-galaxy-s24-s921-sm-s921bzydeub-thumb-539422781",
        "video": "https://www.youtube.com/watch?v=g186XVcuNUc",
        "product_page": "https://www.samsung.com/uk/smartphones/galaxy-s24/",
    },
    {
        "model": "iPad Air 11-inch (M2)", "brand": "Apple", "category": "Tablet", "price": "649.00",
        "image": "https://store.storeimages.cdn-apple.com/4982/as-images.apple.com/is/ipad-air-finish-select-gallery-202405-11inch-blue-wifi?wid=800&hei=1000&fmt=jpeg&qlt=90&.v=1713308270136",
        "product_page": "https://www.apple.com/ipad-air/",
    },
    {
        "model": "Galaxy Tab S9 FE", "brand": "Samsung", "category": "Tablet", "price": "449.00",
        "image": "https://images.samsung.com/is/image/samsung/p6pim/levant/sm-x510nzaemea/gallery/levant-galaxy-tab-s9-fe-x510-sm-x510nzaemea-thumb-538272471?$344_344_PNG$",
        "product_page": "https://www.samsung.com/uk/tablets/galaxy-tab-s/galaxy-tab-s9-fe/",
    },
    {
        "model": "MacBook Air 13-inch (M3)", "brand": "Apple", "category": "Laptop", "price": "999.00",
        "image": "https://store.storeimages.cdn-apple.com/4982/as-images.apple.com/is/macbook-air-13-inch-m3-midnight-witb-202402?wid=800&hei=1000&fmt=jpeg&qlt=90&.v=1707268689716",
        "product_page": "https://www.apple.com/macbook-air-13-and-15/",
    },
    {
        "model": "XPS 13", "brand": "Dell", "category": "Laptop", "price": "1199.00",
        "image": "https://i.dell.com/is/image/DellContent/content/dam/ss2/product-images/page/landing-page/laptop/xps/13/xc9320/desktop/xps-13-laptop-c-00000ff090-gy.psd?fmt=png-alpha&wid=800&hei=1000",
        "product_page": "https://www.dell.com/en-uk/shop/laptops-2-in-1-pcs/scr/laptops/xps",
    },
]


def _catalog_variants(item):
    return list(PhoneModelVariant.objects.filter(
        phone_model__brand__name__iexact=item["brand"],
        phone_model__name__iexact=item["model"],
        is_active=True,
    ).order_by("sort_order", "storage", "color"))


def _unique_slug(base, model):
    slug = slugify(base)
    candidate, index = slug, 2
    while Product.objects.filter(slug=candidate).exclude(pk=getattr(model, "pk", None)).exists():
        candidate = f"{slug}-{index}"
        index += 1
    return candidate


def _unique_sku(base):
    candidate, index = base, 2
    while Product.objects.filter(sku=candidate).exists() or ProductVariant.objects.filter(sku=candidate).exists():
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _variant_price(base, variant_index):
    # Higher storage/RAM configurations carry a realistic refurb uplift.
    return (base + Decimal(variant_index * 35)).quantize(Decimal("0.01"))


@transaction.atomic
def replace_store_catalogue():
    stores = list(Store.objects.filter(is_active=True).select_related("retailer").order_by("created_at")[:2])
    if len(stores) != 2:
        raise RuntimeError(f"Expected exactly two active stores, found {len(stores)}")

    old_product_count = Product.objects.filter(store__in=stores).count()
    # OrderItem.product is PROTECT by design, so historical demo orders must
    # remain readable. Archive those products instead of breaking order history.
    Product.objects.filter(store__in=stores).update(is_active=False, deleted_at=timezone.now(), status=Product.STATUS_REJECTED)

    created = variants_created = media_created = stock_created = 0
    for store in stores:
        warehouse, _ = Warehouse.objects.get_or_create(
            store=store,
            defaults={
                "retailer": store.retailer,
                "name": f"{store.name} Refurbished Devices Warehouse",
                "code": f"{store.slug[:20].upper()}-REFURB",
                "country_code": "DE",
                "is_default": True,
            },
        )
        for index, item in enumerate(STORE_CATALOGUE, start=1):
            category = Category.objects.get(slug=slugify(item["category"]))
            brand, _ = Brand.objects.get_or_create(name=item["brand"], defaults={"slug": slugify(item["brand"])})
            phone_variants = _catalog_variants(item)
            if not phone_variants:
                continue
            base_price = Decimal(item["price"])
            slug = _unique_slug(f"{store.slug}-{item['brand']}-{item['model']}", None)
            sku = _unique_sku(f"{store.slug[:8].upper()}-{slugify(item['model']).replace('-', '')[:18].upper()}-{index:02d}")
            product = Product.objects.create(
                retailer=store.retailer, store=store, category=category, brand=brand,
                name=item["model"], model_name=item["model"], slug=slug, sku=sku,
                product_type=Product.TYPE_VARIANT, price=base_price,
                discount_price=(base_price * Decimal("0.78")).quantize(Decimal("0.01")),
                short_description=f"Certified refurbished {item['brand']} {item['model']} with inspected components.",
                description=(f"Professionally inspected {item['brand']} {item['model']} with verified identity, "
                             "battery and display checks, cleaned hardware, and a 12-month refurbished warranty."),
                seo_title=f"{item['brand']} {item['model']} refurbished in Europe",
                seo_description=f"Buy a quality refurbished {item['brand']} {item['model']} with warranty and tracked delivery.",
                warranty="12-month refurbished warranty", is_featured=index <= 3,
                status=Product.STATUS_APPROVED, is_active=True, approved_at=timezone.now(),
                phone_variant=phone_variants[0],
            )
            created += 1

            for variant_index, phone_variant in enumerate(phone_variants, start=1):
                original = _variant_price(base_price, variant_index - 1)
                sale = (original * Decimal("0.78")).quantize(Decimal("0.01"))
                variant_sku = _unique_sku(f"{sku}-V{variant_index:02d}")
                product_variant = ProductVariant.objects.create(
                    product=product,
                    name=phone_variant.display_name,
                    sku=variant_sku,
                    price=original,
                    discount_price=sale,
                    is_default=variant_index == 1,
                )
                StockItem.objects.create(product=product, variant=product_variant, warehouse=warehouse, on_hand_quantity=8)
                variants_created += 1
                stock_created += 1

            ProductMedia.objects.create(
                product=product, media_type=ProductMedia.TYPE_IMAGE, title="Official product image",
                alt_text=f"{item['brand']} {item['model']}", external_url=item["image"], is_primary=True,
            )
            if item.get("video"):
                ProductMedia.objects.create(
                    product=product, media_type=ProductMedia.TYPE_VIDEO, title="Official product video",
                    alt_text=f"{item['brand']} {item['model']} official video",
                    external_url=item["video"], sort_order=1,
                )
            ProductMedia.objects.create(
                product=product, media_type=ProductMedia.TYPE_IMAGE_360, title="Official product gallery / 360 reference",
                alt_text=f"{item['brand']} {item['model']} product gallery",
                external_url=item["image"], sort_order=2,
            )
            media_created += 2 + int(bool(item.get("video")))

    return {
        "stores": len(stores), "old_products_archived": old_product_count,
        "new_products": created, "variants": variants_created,
        "media_assets": media_created, "stock_items": stock_created,
    }
