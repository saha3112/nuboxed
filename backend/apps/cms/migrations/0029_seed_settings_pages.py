from django.db import migrations


def seed_pages(apps, schema_editor):
    Page = apps.get_model("cms", "Page")
    pages = [
        ("Homepage Settings", "homepage-settings", "Manage homepage content and sections."),
        ("Contact Page Settings", "contact-page-settings", "Customize contact page content and design."),
        ("Product Page Settings", "product-page-settings", "Control storefront product presentation."),
    ]
    for title, slug, content in pages:
        Page.objects.get_or_create(slug=slug, defaults={"title": title, "content": content, "is_published": False, "is_active": True})


class Migration(migrations.Migration):
    dependencies = [("cms", "0028_page_deleted_at")]
    operations = [migrations.RunPython(seed_pages, migrations.RunPython.noop)]
