from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0005_amazonordertracking"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="marketplacelisting",
            unique_together={("connection", "seller_sku")},
        ),
    ]
