from django.db import migrations, models
import django.db.models.deletion
import uuid


def copy_existing_default(apps, schema_editor):
    Global = apps.get_model("orders", "OrderWorkflowGlobalSetting")
    Legacy = apps.get_model("orders", "OrderWorkflowSetting")
    values = {
        "key": "default",
        "auto_invoice": True,
        "allow_manual_invoice": True,
        "auto_label": True,
        "allow_manual_label": True,
        "notify_customer_order_placed": True,
        "notify_customer_status_changed": True,
    }
    legacy = Legacy.objects.order_by("created_at").first()
    if legacy:
        for field in values:
            if field != "key":
                values[field] = getattr(legacy, field)
    Global.objects.get_or_create(key="default", defaults=values)


class Migration(migrations.Migration):
    dependencies = [("orders", "0003_order_workflow_and_delivery_label")]

    operations = [
        migrations.CreateModel(
            name="OrderWorkflowGlobalSetting",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("key", models.CharField(default="default", max_length=32, unique=True)),
                ("auto_invoice", models.BooleanField(default=True)),
                ("allow_manual_invoice", models.BooleanField(default=True)),
                ("auto_label", models.BooleanField(default=True)),
                ("allow_manual_label", models.BooleanField(default=True)),
                ("notify_customer_order_placed", models.BooleanField(default=True)),
                ("notify_customer_status_changed", models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name="OrderWorkflowStoreOverride",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("auto_invoice", models.BooleanField(default=True)),
                ("allow_manual_invoice", models.BooleanField(default=True)),
                ("auto_label", models.BooleanField(default=True)),
                ("allow_manual_label", models.BooleanField(default=True)),
                ("notify_customer_order_placed", models.BooleanField(default=True)),
                ("notify_customer_status_changed", models.BooleanField(default=True)),
                ("store", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="order_workflow_override", to="stores.store")),
            ],
        ),
        migrations.RunPython(copy_existing_default, migrations.RunPython.noop),
    ]
