from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("settings_app", "0019_salecountdownsetting_deleted_at")]
    operations = [migrations.AddField(
        model_name="salecountdownsetting", name="starts_at",
        field=models.DateTimeField(blank=True, null=True),
    )]
