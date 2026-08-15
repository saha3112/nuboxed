from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("inventory", "0003_initial")]

    operations = [
        migrations.AlterField(
            model_name="deliverylocation",
            name="postal_code",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name="deliverylocation",
            name="postal_code_prefix",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
