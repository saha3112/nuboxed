from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("inventory", "0004_expand_delivery_location_postal_codes")]

    operations = [migrations.DeleteModel(name="DeliveryHoliday")]
