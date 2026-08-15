from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("settings_app", "0024_brandsettings_favicon"),
    ]

    operations = [
        migrations.AddField(
            model_name="brandsettings",
            name="drawer_menu_logo",
            field=models.ImageField(
                blank=True,
                help_text="Custom logo shown at the top of the storefront mobile/tablet drawer menu.",
                null=True,
                upload_to="logos/drawer/",
                verbose_name="Drawer menu logo",
            ),
        ),
    ]
