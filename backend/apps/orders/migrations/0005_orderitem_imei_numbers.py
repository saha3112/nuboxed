from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0004_global_workflow_and_store_overrides")]
    operations = [migrations.AddField(
        model_name="orderitem", name="imei_numbers", field=models.JSONField(blank=True, default=list),
    )]
