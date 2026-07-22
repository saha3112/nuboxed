from django.db import migrations


def create_default_home_slider(apps, schema_editor):
    Slider = apps.get_model("cms", "Slider")
    if Slider.objects.exists():
        return
    Slider.objects.create(
        title="Everything you need, beautifully curated.",
        subtitle="Shop verified products from trusted retailers with clear pricing, secure checkout and dependable delivery.",
        eyebrow="Nuboxed marketplace",
        cta_label="Shop collection",
        cta_url="/products/",
        meta_primary_title="Verified",
        meta_primary_text="product data",
        meta_secondary_title="Secure",
        meta_secondary_text="checkout",
        status="published",
        sort_order=0,
        is_active=True,
    )


def remove_default_home_slider(apps, schema_editor):
    Slider = apps.get_model("cms", "Slider")
    Slider.objects.filter(
        title="Everything you need, beautifully curated.",
        eyebrow="Nuboxed marketplace",
        cta_url="/products/",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("cms", "0003_slider_eyebrow_slider_meta_primary_text_and_more")]

    operations = [migrations.RunPython(create_default_home_slider, remove_default_home_slider)]
