from django.db import migrations


def publish_settings_pages(apps, schema_editor):
    Page = apps.get_model("cms", "Page")
    Page.objects.filter(slug__in=["homepage-settings", "contact-page-settings", "product-page-settings"], deleted_at__isnull=True).update(is_published=True)


class Migration(migrations.Migration):
    dependencies = [("cms", "0029_seed_settings_pages")]
    operations = [migrations.RunPython(publish_settings_pages, migrations.RunPython.noop)]
