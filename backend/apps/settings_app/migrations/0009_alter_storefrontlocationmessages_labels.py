from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("settings_app", "0008_storefrontlocationmessages")]

    operations = [
        migrations.AlterField(
            model_name="storefrontlocationmessages",
            name="no_stores_message",
            field=models.CharField(
                default="No more stores found in your current location.",
                help_text="Message shown above the alternate-location button on the Stores page.",
                max_length=255,
                verbose_name="No nearby stores message",
            ),
        ),
        migrations.AlterField(
            model_name="storefrontlocationmessages",
            name="other_location_message",
            field=models.CharField(
                default="Do you want to see stores from stores in another location?",
                help_text="Button text that lets visitors view stores from another location.",
                max_length=255,
                verbose_name="Other location button text",
            ),
        ),
    ]
