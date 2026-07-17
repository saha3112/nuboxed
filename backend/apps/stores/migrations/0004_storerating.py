from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0003_store_page_builder"),
    ]

    operations = [
        migrations.CreateModel(
            name="StoreRating",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("reviewer_name", models.CharField(max_length=120)),
                ("rating", models.PositiveSmallIntegerField(default=5)),
                ("comment", models.TextField(blank=True)),
                ("is_approved", models.BooleanField(default=True)),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ratings", to="stores.store")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
