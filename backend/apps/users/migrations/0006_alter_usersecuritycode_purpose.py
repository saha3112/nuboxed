from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("users", "0005_userpaymentmethod_country_code")]

    operations = [
        migrations.AlterField(
            model_name="usersecuritycode",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("email_verification", "Email verification"),
                    ("email_change", "Email change verification"),
                    ("password_reset", "Password reset"),
                    ("login_otp", "Login OTP"),
                ],
                max_length=32,
            ),
        ),
    ]
