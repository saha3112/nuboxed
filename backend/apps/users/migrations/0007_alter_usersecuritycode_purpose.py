from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("users", "0006_alter_usersecuritycode_purpose")]

    operations = [
        migrations.AlterField(
            model_name="usersecuritycode",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("email_verification", "Email verification"),
                    ("email_change", "Email change verification"),
                    ("password_change", "Password change verification"),
                    ("password_reset", "Password reset"),
                    ("login_otp", "Login OTP"),
                ],
                max_length=32,
            ),
        ),
    ]
