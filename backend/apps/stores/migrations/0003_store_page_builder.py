from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0002_store_currency_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="store_page_announcement",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="store",
            name="store_page_sections",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="store",
            name="store_page_tagline",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
