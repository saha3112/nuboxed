from django.db import migrations


def seed_nuboxed_site_logo(apps, schema_editor):
    SiteLogo = apps.get_model("settings_app", "SiteLogo")
    logo_path = "logos/nuboxed-logo.webp"
    SiteLogo.objects.exclude(logo_image=logo_path).update(is_active=False)
    SiteLogo.objects.update_or_create(
        logo_image=logo_path,
        defaults={
            "alt_text": "Nuboxed",
            "is_active": True,
        },
    )


def unseed_nuboxed_site_logo(apps, schema_editor):
    SiteLogo = apps.get_model("settings_app", "SiteLogo")
    SiteLogo.objects.filter(logo_image="logos/nuboxed-logo.webp").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("settings_app", "0004_menuitem_sitelogo_sociallink"),
    ]

    operations = [
        migrations.RunPython(seed_nuboxed_site_logo, unseed_nuboxed_site_logo),
    ]
