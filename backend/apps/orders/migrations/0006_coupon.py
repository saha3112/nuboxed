from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0005_orderitem_imei_numbers"),
        ("retailers", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Coupon",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False, editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("code", models.CharField(max_length=64, unique=True)),
                ("discount_type", models.CharField(choices=[("percentage", "Percentage"), ("fixed", "Fixed amount")], default="percentage", max_length=20)),
                ("discount_value", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("minimum_order_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("maximum_discount_amount", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
                ("usage_limit", models.PositiveIntegerField(blank=True, null=True)),
                ("used_count", models.PositiveIntegerField(default=0)),
                ("retailer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="coupons", to="retailers.retailer")),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
