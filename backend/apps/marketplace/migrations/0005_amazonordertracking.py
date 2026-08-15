from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0004_marketplacestoremapping"),
        ("catalog", "0017_category_category_image_alt_and_more"),
        ("orders", "0007_alter_coupon_id_alter_deliverylabel_generated_at_and_more"),
        ("retailers", "0005_retailer_can_approve_reviews"),
        ("stores", "0005_storerating_is_active"),
    ]

    operations = [
        migrations.CreateModel(
            name="AmazonOrderTracking",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)), ("is_active", models.BooleanField(default=True)),
                ("external_order_id", models.CharField(max_length=120)), ("amazon_order_status", models.CharField(blank=True, max_length=64)),
                ("fulfillment_status", models.CharField(blank=True, max_length=64)), ("attribution_status", models.CharField(default="pending", max_length=32)),
                ("marketplace_id", models.CharField(blank=True, max_length=80)), ("purchase_date", models.DateTimeField(blank=True, null=True)),
                ("order_total", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)), ("currency_code", models.CharField(blank=True, max_length=3)),
                ("shipping_city", models.CharField(blank=True, max_length=120)), ("shipping_country_code", models.CharField(blank=True, max_length=2)),
                ("raw_payload", models.JSONField(blank=True, default=dict)), ("last_seen_at", models.DateTimeField(blank=True, null=True)), ("imported_at", models.DateTimeField(blank=True, null=True)),
                ("connection", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="amazon_orders", to="marketplace.marketplaceconnection")),
                ("retailer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="amazon_order_tracking", to="retailers.retailer")),
                ("store", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="amazon_order_tracking", to="stores.store")),
                ("local_order", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="amazon_tracking_records", to="orders.order")),
            ],
            options={"ordering": ("-purchase_date", "-created_at"), "unique_together": {("connection", "external_order_id")}, "indexes": [models.Index(fields=["retailer", "amazon_order_status"], name="marketplace_retaile_af6a83_idx"), models.Index(fields=["store", "purchase_date"], name="marketplace_store_i_3a16e7_idx")]},
        ),
        migrations.CreateModel(
            name="AmazonOrderItemTracking",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)), ("is_active", models.BooleanField(default=True)),
                ("seller_sku", models.CharField(blank=True, max_length=120)), ("title", models.CharField(blank=True, max_length=255)), ("quantity", models.PositiveIntegerField(default=0)),
                ("item_total", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)), ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("tracking_order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="marketplace.amazonordertracking")),
                ("product", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="amazon_order_items", to="catalog.product")),
                ("variant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="amazon_order_items", to="catalog.productvariant")),
                ("retailer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="amazon_order_items", to="retailers.retailer")),
                ("store", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="amazon_order_items", to="stores.store")),
            ],
        ),
    ]
