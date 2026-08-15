from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("settings_app", "0015_brandsettings_location_prompt_enabled"),
    ]

    operations = [
        migrations.AddField(
            model_name="brandsettings",
            name="fixed_menu_logo",
            field=models.ImageField(
                blank=True,
                help_text="Logo shown at the left of the storefront menu when visitors scroll.",
                null=True,
                upload_to="logos/",
                verbose_name="Fixed storefront menu logo",
            ),
        ),
    ]
