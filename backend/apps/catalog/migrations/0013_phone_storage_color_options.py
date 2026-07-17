from django.db import migrations, models
import uuid


def seed_phone_options(apps, schema_editor):
    PhoneModelVariant = apps.get_model("catalog", "PhoneModelVariant")
    PhoneStorageOption = apps.get_model("catalog", "PhoneStorageOption")
    PhoneColorOption = apps.get_model("catalog", "PhoneColorOption")

    storage_seen = set()
    color_seen = set()
    storage_sort = 0
    color_sort = 0

    for variant in PhoneModelVariant.objects.all().order_by("sort_order", "storage", "color"):
        storage = (variant.storage or "").strip()
        if storage and storage.lower() not in storage_seen:
            storage_seen.add(storage.lower())
            PhoneStorageOption.objects.get_or_create(
                label=storage,
                defaults={"sort_order": storage_sort, "is_active": True},
            )
            storage_sort += 10

        color = (variant.color or "").strip()
        if color and color.lower() not in color_seen:
            color_seen.add(color.lower())
            PhoneColorOption.objects.get_or_create(
                name=color,
                defaults={
                    "color_hex": (variant.color_hex or "").strip(),
                    "sort_order": color_sort,
                    "is_active": True,
                },
            )
            color_sort += 10


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0012_productreview"),
    ]

    operations = [
        migrations.CreateModel(
            name="PhoneColorOption",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("is_active", models.BooleanField(default=True)),
                ("name", models.CharField(help_text="e.g. Midnight Black, Starlight", max_length=80, unique=True)),
                ("color_hex", models.CharField(blank=True, help_text="#rrggbb", max_length=7)),
                ("sort_order", models.PositiveIntegerField(default=0)),
            ],
            options={
                "ordering": ["sort_order", "name"],
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="PhoneStorageOption",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("is_active", models.BooleanField(default=True)),
                ("label", models.CharField(help_text="e.g. 128GB, 256GB, 1TB", max_length=30, unique=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
            ],
            options={
                "ordering": ["sort_order", "label"],
                "abstract": False,
            },
        ),
        migrations.RunPython(seed_phone_options, migrations.RunPython.noop),
    ]
