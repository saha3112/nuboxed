from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("settings_app", "0020_salecountdownsetting_starts_at")]
    operations = [
        migrations.AddField(model_name="salecountdownsetting", name="product", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="sale_countdown_settings", to="catalog.product")),
        migrations.AddField(model_name="salecountdownsetting", name="variant", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="sale_countdown_settings", to="catalog.productvariant")),
        migrations.AddField(model_name="salecountdownsetting", name="discount_percentage", field=models.DecimalField(decimal_places=2, default=0, max_digits=5)),
    ]
