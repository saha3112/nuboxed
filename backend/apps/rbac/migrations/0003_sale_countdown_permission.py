from django.db import migrations


def create_sale_countdown_permission(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Permission.objects.get_or_create(
        code="sale_countdown.manage",
        defaults={"name": "Manage sale countdown settings"},
    )


class Migration(migrations.Migration):
    dependencies = [("rbac", "0002_initial")]
    operations = [migrations.RunPython(create_sale_countdown_permission, migrations.RunPython.noop)]
