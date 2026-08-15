import uuid

from django.db import migrations, models


DOCUMENTS = [
    ("business_document", "Business Registration", "Upload your business registration certificate.", "ph ph-certificate", 10),
    ("gst_certificate", "GST Certificate", "Upload your GST or tax registration certificate.", "ph ph-receipt", 20),
    ("pan_card", "PAN Card / Tax ID", "Upload your PAN card or tax identification document.", "ph ph-identification-card", 30),
    ("cancelled_cheque", "Cancelled Cheque", "Upload a cancelled cheque or bank statement.", "ph ph-bank", 40),
    ("address_proof", "Address Proof", "Upload a valid utility bill or address proof.", "ph ph-map-pin-area", 50),
    ("signature", "Authorized Signature", "Upload the authorized signatory signature.", "ph ph-pen-nib", 60),
    ("msme_certificate", "MSME / Udyam Certificate", "Upload your MSME or Udyam certificate, if applicable.", "ph ph-factory", 70),
    ("fssai_license", "FSSAI License", "Upload your FSSAI license, if applicable.", "ph ph-cookie", 80),
]


def seed_settings(apps, schema_editor):
    Page = apps.get_model("retailers", "SellerVerificationPageSetting")
    Document = apps.get_model("retailers", "SellerVerificationDocumentSetting")
    Page.objects.get_or_create(
        singleton_key="registration",
        defaults={
            "section_title": "Seller Verification Documents",
            "section_description": "Upload documents to speed up your seller verification. All documents are optional during registration — you can upload them later from your profile.",
            "is_visible": True,
            "is_active": True,
        },
    )
    for field_name, title, description, icon_class, sort_order in DOCUMENTS:
        Document.objects.get_or_create(
            field_name=field_name,
            defaults={
                "title": title,
                "description": description,
                "icon_class": icon_class,
                "sort_order": sort_order,
                "is_visible": True,
                "is_required": False,
                "is_active": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("retailers", "0005_retailer_can_approve_reviews")]

    operations = [
        migrations.CreateModel(
            name="SellerVerificationPageSetting",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("singleton_key", models.CharField(default="registration", max_length=32, unique=True)),
                ("section_title", models.CharField(default="Seller Verification Documents", max_length=160)),
                ("section_description", models.TextField(blank=True, default="Upload documents to speed up your seller verification. All documents are optional during registration — you can upload them later from your profile.")),
                ("is_visible", models.BooleanField(default=True)),
            ],
            options={"verbose_name": "Seller verification page setting", "verbose_name_plural": "Seller verification page settings"},
        ),
        migrations.CreateModel(
            name="SellerVerificationDocumentSetting",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("field_name", models.CharField(max_length=64, unique=True)),
                ("title", models.CharField(max_length=160)),
                ("description", models.CharField(blank=True, max_length=320)),
                ("icon_class", models.CharField(default="ph ph-file", max_length=100)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_visible", models.BooleanField(default=True)),
                ("is_required", models.BooleanField(default=False)),
            ],
            options={"ordering": ("sort_order", "title"), "verbose_name": "Seller verification document", "verbose_name_plural": "Seller verification documents"},
        ),
        migrations.RunPython(seed_settings, migrations.RunPython.noop),
    ]
