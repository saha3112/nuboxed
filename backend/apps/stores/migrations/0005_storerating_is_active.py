from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0004_storerating"),
    ]

    operations = [
        migrations.AddField(
            model_name="storerating",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]
