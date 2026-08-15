import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("retailers", "0006_seller_verification_settings")]

    operations = [
        migrations.CreateModel(
            name="SellerVerificationDocumentUpload",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("file", models.FileField(upload_to="retailer/documents/")),
                ("retailer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="additional_verification_documents", to="retailers.retailer")),
                ("setting", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="uploads", to="retailers.sellerverificationdocumentsetting")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("retailer", "setting"), name="unique_retailer_verification_upload")]},
        ),
    ]
