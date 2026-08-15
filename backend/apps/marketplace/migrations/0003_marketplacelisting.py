from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0002_marketplaceconnection_marketplacewebhookevent_and_more"),
        ("catalog", "0017_category_category_image_alt_and_more"),
        ("inventory", "0003_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MarketplaceListing",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("is_active", models.BooleanField(default=True)),
                ("seller_sku", models.CharField(max_length=120)),
                ("external_listing_id", models.CharField(blank=True, max_length=255)),
                ("marketplace_id", models.CharField(blank=True, max_length=80)),
                ("status", models.CharField(default="pending", max_length=32)),
                ("last_pushed_quantity", models.IntegerField(blank=True, null=True)),
                ("last_pushed_at", models.DateTimeField(blank=True, null=True)),
                ("last_pulled_quantity", models.IntegerField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
                ("connection", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="listings", to="marketplace.marketplaceconnection")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="marketplace_listings", to="catalog.product")),
                ("variant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="marketplace_listings", to="catalog.productvariant")),
                ("fulfillment_location", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="marketplace_listings", to="inventory.warehouse")),
            ],
            options={"ordering": ("seller_sku",), "unique_together": {("connection", "seller_sku"), ("connection", "product", "variant")}},
        ),
    ]
