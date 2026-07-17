from django.db import migrations, models

import apps.catalog.models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0014_phoneramoption_alter_phonemodelvariant_options_and_more")]

    operations = [
        migrations.AddField(
            model_name="product",
            name="sale_title",
            field=models.CharField(default="Hurry up! Sale ends in:", blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="product",
            name="sale_ends_at",
            field=models.DateTimeField(default=apps.catalog.models.default_sale_ends_at, blank=True, null=True),
        ),
    ]
