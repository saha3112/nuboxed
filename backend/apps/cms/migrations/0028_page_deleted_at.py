from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cms", "0027_dynamicform_captcha_enabled")]

    operations = [migrations.AddField(
        model_name="page",
        name="deleted_at",
        field=models.DateTimeField(blank=True, null=True),
    )]
