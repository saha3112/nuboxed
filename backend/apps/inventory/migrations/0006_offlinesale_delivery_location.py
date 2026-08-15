from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("inventory", "0005_remove_deliveryholiday")]

    operations = [
        migrations.AddField(
            model_name="offlinesale",
            name="delivery_location",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="offline_sales",
                to="inventory.deliverylocation",
            ),
        ),
    ]
