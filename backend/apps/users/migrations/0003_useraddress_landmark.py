from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0002_privacyrequest_gdprconsent"),
    ]

    operations = [
        migrations.AddField(
            model_name="useraddress",
            name="landmark",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
