from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("settings_app", "0018_alter_megamenusettings_hover_color")]

    operations = [
        migrations.AddField(
            model_name="salecountdownsetting",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
