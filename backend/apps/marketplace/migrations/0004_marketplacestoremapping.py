from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0003_marketplacelisting"), ("stores", "0001_initial"), ("inventory", "0003_initial")]

    operations = [
        migrations.CreateModel(
            name="MarketplaceStoreMapping",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("is_active", models.BooleanField(default=True)),
                ("amazon_store_code", models.CharField(blank=True, max_length=120)),
                ("is_enabled", models.BooleanField(default=True)),
                ("last_sync_at", models.DateTimeField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True)),
                ("connection", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="store_mappings", to="marketplace.marketplaceconnection")),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="marketplace_store_mappings", to="stores.store")),
                ("warehouse", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="marketplace_store_mappings", to="inventory.warehouse")),
            ],
            options={"ordering": ("store__name",), "unique_together": {("connection", "store")}},
        ),
    ]
