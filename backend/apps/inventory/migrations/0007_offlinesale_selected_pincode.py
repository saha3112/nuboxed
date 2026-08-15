from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("inventory", "0006_offlinesale_delivery_location")]
    operations = [migrations.AddField(
        model_name="offlinesale", name="selected_pincode",
        field=models.CharField(blank=True, max_length=32),
    )]
