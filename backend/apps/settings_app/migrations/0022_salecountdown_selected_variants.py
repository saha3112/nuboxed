from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("settings_app", "0021_salecountdown_scope_and_discount")]
    operations = [migrations.AddField(
        model_name="salecountdownsetting", name="selected_variant_ids",
        field=models.JSONField(blank=True, default=list),
    )]
