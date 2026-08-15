from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("settings_app", "0016_brandsettings_fixed_menu_logo"),
    ]

    operations = [
        migrations.AddField(
            model_name="brandsettings",
            name="email_logo",
            field=models.ImageField(
                blank=True,
                help_text="Logo used in OTP and notification emails. Falls back to the storefront logo when empty.",
                null=True,
                upload_to="logos/email/",
            ),
        ),
    ]
