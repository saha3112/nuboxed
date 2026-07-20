# Generated manually for the payment-method country association.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("users", "0004_userpaymentmethod")]

    operations = [
        migrations.AddField(
            model_name="userpaymentmethod",
            name="country_code",
            field=models.CharField(default="DE", max_length=2),
        ),
    ]
