import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.users.models import User
from apps.retailers.models import Retailer
from apps.catalog.models import Category, Product, ProductVariant
from apps.inventory.models import Warehouse, StockItem
from apps.stores.models import Store

print("Starting to seed more dummy data...")

retailer_user = User.objects.get(email='retailer@nuboxed.com')
retailer = Retailer.objects.get(support_email=retailer_user.email)
store = Store.objects.get(retailer=retailer, name="Test Store")
warehouse = Warehouse.objects.get(retailer=retailer, code="WH-01")

# Categories & Subcategories
cat_home, _ = Category.objects.get_or_create(name="Home & Kitchen", slug="home-kitchen")
cat_furniture, _ = Category.objects.get_or_create(name="Furniture", slug="furniture", parent=cat_home)
cat_appliances, _ = Category.objects.get_or_create(name="Appliances", slug="appliances", parent=cat_home)

cat_sports, _ = Category.objects.get_or_create(name="Sports & Outdoors", slug="sports-outdoors")
cat_fitness, _ = Category.objects.get_or_create(name="Fitness", slug="fitness", parent=cat_sports)

# Electronics category exists
cat_electronics = Category.objects.get(slug="electronics")
cat_smartphones, _ = Category.objects.get_or_create(name="Smartphones", slug="smartphones", parent=cat_electronics)

# Products
more_products = [
    {
        "name": "Modern Sofa",
        "slug": "modern-sofa",
        "category": cat_furniture,
        "price": Decimal("499.99"),
        "sku": "PROD-FURN-01",
        "variants": [("Sofa-Grey", "SOFA-GRY-01", Decimal("499.99")), ("Sofa-Blue", "SOFA-BLU-01", Decimal("549.99"))]
    },
    {
        "name": "Coffee Maker",
        "slug": "coffee-maker",
        "category": cat_appliances,
        "price": Decimal("89.99"),
        "sku": "PROD-APP-01",
        "variants": [("Default", "CM-DEF-01", Decimal("89.99"))]
    },
    {
        "name": "Yoga Mat",
        "slug": "yoga-mat",
        "category": cat_fitness,
        "price": Decimal("25.00"),
        "sku": "PROD-FIT-01",
        "variants": [("Yoga-Mat-Black", "YM-BLK-01", Decimal("25.00")), ("Yoga-Mat-Pink", "YM-PNK-01", Decimal("25.00"))]
    },
    {
        "name": "Smartphone Pro Max",
        "slug": "smartphone-pro-max",
        "category": cat_smartphones,
        "price": Decimal("1099.00"),
        "sku": "PROD-ELEC-02",
        "variants": [("256GB Black", "SP-256-BLK", Decimal("1099.00")), ("512GB Silver", "SP-512-SLV", Decimal("1299.00"))]
    },
    {
        "name": "Dumbbell Set",
        "slug": "dumbbell-set",
        "category": cat_fitness,
        "price": Decimal("45.00"),
        "sku": "PROD-FIT-02",
        "variants": [("10 lbs", "DB-10-LB", Decimal("45.00")), ("20 lbs", "DB-20-LB", Decimal("85.00"))]
    }
]

for pdata in more_products:
    prod, _ = Product.objects.get_or_create(
        name=pdata["name"],
        slug=pdata["slug"],
        retailer=retailer,
        store=store,
        category=pdata["category"],
        defaults={
            'description': f"High quality {pdata['name']}",
            'price': pdata["price"],
            'sku': pdata["sku"],
            'status': 'approved'
        }
    )
    
    for vname, vsku, vprice in pdata["variants"]:
        variant, _ = ProductVariant.objects.get_or_create(
            product=prod,
            sku=vsku,
            defaults={'name': vname, 'price': vprice}
        )
        # Add stock
        StockItem.objects.update_or_create(
            product=prod,
            variant=variant,
            warehouse=warehouse,
            defaults={'on_hand_quantity': 100}
        )

print("Additional products, categories and subcategories successfully added!")
