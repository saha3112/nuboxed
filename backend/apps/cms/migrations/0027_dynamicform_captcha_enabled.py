from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0026_seed_contact_support_form"),
    ]

    operations = [
        migrations.AddField(
            model_name="dynamicform",
            name="captcha_enabled",
            field=models.BooleanField(default=False, help_text="Show the configured captcha on this public form."),
        ),
    ]
