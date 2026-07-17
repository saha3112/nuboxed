from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [("orders", "0002_initial"), ("retailers", "0005_retailer_can_approve_reviews"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="OrderWorkflowSetting",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)), ("auto_invoice", models.BooleanField(default=True)),
                ("allow_manual_invoice", models.BooleanField(default=True)), ("auto_label", models.BooleanField(default=True)),
                ("allow_manual_label", models.BooleanField(default=True)),
                ("notify_customer_order_placed", models.BooleanField(default=True)),
                ("notify_customer_status_changed", models.BooleanField(default=True)),
                ("retailer", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="order_workflow_setting", to="retailers.retailer")),
            ],
        ),
        migrations.CreateModel(
            name="DeliveryLabel",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)), ("label_number", models.CharField(max_length=64, unique=True)),
                ("status", models.CharField(choices=[("generated", "Generated"), ("printed", "Printed")], default="generated", max_length=20)),
                ("payload", models.JSONField(blank=True, default=dict)), ("generated_at", models.DateTimeField()),
                ("printed_at", models.DateTimeField(blank=True, null=True)),
                ("generated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("order", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="delivery_label", to="orders.order")),
            ],
        ),
    ]
