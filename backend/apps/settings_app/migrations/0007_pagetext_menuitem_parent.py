import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("settings_app", "0006_megamenusettings")]

    operations = [
        migrations.AddField(
            model_name="menuitem",
            name="parent",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="children", to="settings_app.menuitem"),
        ),
        migrations.CreateModel(
            name="PageText",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("key", models.SlugField(help_text="Stable key used by storefront templates, e.g. stores", max_length=80, unique=True)),
                ("title", models.CharField(max_length=160)),
                ("breadcrumb_label", models.CharField(blank=True, max_length=160)),
                ("menu_label", models.CharField(blank=True, max_length=100)),
            ],
            options={"verbose_name": "Storefront Page Text", "verbose_name_plural": "Storefront Page Texts", "ordering": ("key",)},
        ),
        migrations.RunPython(
            lambda apps, schema_editor: apps.get_model("settings_app", "PageText").objects.get_or_create(
                key="stores",
                defaults={"title": "Store Directory", "breadcrumb_label": "Stores", "menu_label": "Stores"},
            ),
            migrations.RunPython.noop,
        ),
    ]
