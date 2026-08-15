from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("inventory", "0007_offlinesale_selected_pincode")]
    operations = [migrations.AddField(
        model_name="deliverylocation",
        name="pin_details",
        field=models.JSONField(blank=True, default=dict),
    )]
