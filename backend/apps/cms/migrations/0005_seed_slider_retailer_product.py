from django.db import migrations


def assign_default_retailer_product(apps, schema_editor):
    Slider = apps.get_model("cms", "Slider")
    Retailer = apps.get_model("retailers", "Retailer")
    Product = apps.get_model("catalog", "Product")
    retailer = Retailer.objects.filter(status="approved", is_active=True).order_by("created_at").first()
    if not retailer:
        return
    product = Product.objects.filter(
        retailer_id=retailer.pk,
        status="approved",
        is_active=True,
    ).order_by("created_at").first()
    if not product:
        return
    Slider.objects.filter(
        title="Everything you need, beautifully curated.",
        product__isnull=True,
    ).update(retailer_id=retailer.pk, product_id=product.pk)


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0004_seed_default_home_slider"),
        ("catalog", "0017_category_category_image_alt_and_more"),
        ("retailers", "0005_retailer_can_approve_reviews"),
    ]

    operations = [migrations.RunPython(assign_default_retailer_product, migrations.RunPython.noop)]
