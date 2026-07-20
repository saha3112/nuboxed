from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0003_useraddress_landmark"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserPaymentMethod",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("method_type", models.CharField(choices=[("card", "Credit or debit card"), ("upi", "UPI"), ("bank", "Bank account"), ("wallet", "Digital wallet")], max_length=20)),
                ("display_name", models.CharField(max_length=120)),
                ("last4", models.CharField(blank=True, max_length=4)),
                ("expiry", models.CharField(blank=True, max_length=7)),
                ("is_default", models.BooleanField(default=False)),
                ("user", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="payment_methods", to="users.user")),
            ],
            options={"ordering": ("-is_default", "-updated_at")},
        ),
    ]
