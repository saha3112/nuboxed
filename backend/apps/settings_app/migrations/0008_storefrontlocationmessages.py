import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("settings_app", "0007_pagetext_menuitem_parent")]

    operations = [
        migrations.CreateModel(
            name="StorefrontLocationMessages",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("no_stores_message", models.CharField(default="No more stores found in your current location.", help_text="Message shown above the alternate-location button on the Stores page.", max_length=255)),
                ("other_location_message", models.CharField(default="Do you want to see stores from stores in another location?", help_text="Button text that lets visitors view stores from another location.", max_length=255)),
            ],
            options={"verbose_name": "Stores Location Messages", "verbose_name_plural": "Stores Location Messages"},
        ),
        migrations.RunPython(
            lambda apps, schema_editor: apps.get_model("settings_app", "StorefrontLocationMessages").objects.create(),
            migrations.RunPython.noop,
        ),
    ]
