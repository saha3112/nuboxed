from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("settings_app", "0023_salecountdownsetting_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="brandsettings",
            name="favicon",
            field=models.ImageField(
                blank=True,
                help_text="Browser tab icon. Use a square PNG, ICO, or SVG-compatible image (32x32 or 48x48 recommended).",
                null=True,
                upload_to="logos/favicon/",
            ),
        ),
    ]
