from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("settings_app", "0022_salecountdown_selected_variants"),
    ]

    operations = [
        migrations.AddField(
            model_name="salecountdownsetting",
            name="name",
            field=models.CharField(
                default="Sale Countdown",
                help_text="Internal name used to identify this sale rule in the backend.",
                max_length=160,
            ),
        ),
    ]
