import uuid

from django.db import migrations, models


FIELDS = [
    ("vat_number", "GST / VAT / Tax ID (Optional)", "e.g. GSTIN12345", "text", 10),
    ("business_type", "Type of Entity (Optional)", "Select Business Type...", "select", 20),
    ("business_address", "Street Address (Optional)", "123 Business Rd, Suite 100", "textarea", 30),
]


def seed_fields(apps, schema_editor):
    Setting = apps.get_model("retailers", "RetailerRegistrationFieldSetting")
    for name, title, placeholder, field_type, order in FIELDS:
        Setting.objects.get_or_create(field_name=name, defaults={"title": title, "placeholder": placeholder, "field_type": field_type, "sort_order": order, "is_system": True, "is_visible": True})


class Migration(migrations.Migration):
    dependencies = [("retailers", "0007_seller_verification_document_upload")]
    operations = [
        migrations.AddField(model_name="retailer", name="custom_registration_data", field=models.JSONField(blank=True, default=dict)),
        migrations.CreateModel(
            name="RetailerRegistrationFieldSetting",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("is_active", models.BooleanField(default=True)),
                ("field_name", models.CharField(max_length=64, unique=True)), ("title", models.CharField(max_length=160)), ("placeholder", models.CharField(blank=True, max_length=255)),
                ("field_type", models.CharField(choices=[("text", "Text"), ("textarea", "Textarea"), ("select", "Select")], default="text", max_length=16)),
                ("choices_text", models.TextField(blank=True, help_text="One option per line for Select fields")), ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_visible", models.BooleanField(default=True)), ("is_required", models.BooleanField(default=False)), ("is_system", models.BooleanField(default=False)),
            ], options={"ordering": ("sort_order", "title")},
        ),
        migrations.RunPython(seed_fields, migrations.RunPython.noop),
    ]
