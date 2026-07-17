from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.mail import send_mail
from django.db import transaction
from django.utils.text import slugify

from apps.rbac.services import assign_customer_role
from apps.users.models import User, UserSecurityCode
from apps.notifications.services import send_notification_event


def generate_unique_username(email):
    base_username = slugify(email.split("@")[0]).replace("-", "_") or "user"
    username = base_username
    index = 1
    while User.objects.filter(username=username).exists():
        index += 1
        username = f"{base_username}{index}"
    return username


@transaction.atomic
def register_user(validated_data):
    password = validated_data.pop("password")
    validate_password(password)

    if not validated_data.get("username"):
        validated_data["username"] = generate_unique_username(validated_data["email"])

    user = User.objects.create_user(password=password, **validated_data)
    assign_customer_role(user)
    from django.contrib.auth import get_user_model
    admin_emails = list(get_user_model().objects.filter(is_superuser=True, is_active=True).exclude(email="").values_list("email", flat=True))
    send_notification_event("user_registered", {"email": user.email, "name": user.get_full_name() or user.username}, user=user, extra_recipients=admin_emails)
    return user


def issue_security_code(user, purpose, channel=UserSecurityCode.CHANNEL_EMAIL):
    code_record = UserSecurityCode.issue(user=user, purpose=purpose, channel=channel)
    send_mail(
        subject=f"CommerceOS {purpose.replace('_', ' ').title()} Code",
        message=f"Your CommerceOS verification code is {code_record.code}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )
    return code_record
