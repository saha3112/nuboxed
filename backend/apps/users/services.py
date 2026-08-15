from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from io import BytesIO
from email.mime.image import MIMEImage
from PIL import Image

from django.core.mail import EmailMultiAlternatives, get_connection, send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils.text import slugify

from apps.rbac.services import assign_customer_role
from apps.users.models import User, UserSecurityCode
from apps.notifications.services import send_notification_event
from apps.settings_app.models import Setting
from apps.settings_app.models import BrandSettings


def _email_logo_image(logo_field):
    """Embed uploaded logos as PNG so transparent WebP files render correctly in email clients."""
    with logo_field.open("rb") as logo_file:
        source = logo_file.read()
    try:
        image = Image.open(BytesIO(source)).convert("RGBA")
        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        return MIMEImage(output.getvalue(), _subtype="png")
    except (OSError, ValueError):
        return MIMEImage(source)


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


def issue_security_code(user, purpose, channel=UserSecurityCode.CHANNEL_EMAIL, recipient_email=None):
    code_record = UserSecurityCode.issue(user=user, purpose=purpose, channel=channel)
    mail_config = Setting.objects.filter(
        key="email_settings", is_active=True
    ).values_list("value", flat=True).first() or {}
    connection = None
    if mail_config.get("host"):
        connection = get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=mail_config["host"],
            port=mail_config.get("port") or 587,
            username=mail_config.get("username") or None,
            password=mail_config.get("password") or None,
            use_tls=bool(mail_config.get("use_tls")),
            use_ssl=bool(mail_config.get("use_ssl")),
            timeout=mail_config.get("timeout") or 30,
            fail_silently=False,
        )
    brand = BrandSettings.objects.filter(is_active=True).first()
    brand_name = brand.brand_name if brand else "Nuboxed"
    logo_field = None
    if brand:
        logo_field = brand.email_logo or brand.fixed_menu_logo or brand.logo_big or brand.logo_small

    subject = f"{brand_name} Email Verification Code"
    text_body = (
        f"Hi {user.get_full_name() or user.username},\n\n"
        f"Your {brand_name} verification code is {code_record.code}.\n"
        "This code expires in 15 minutes.\n\n"
        f"If you did not create a {brand_name} account, you can ignore this email."
    )
    html_body = render_to_string("emails/verification_code.html", {
        "brand_name": brand_name,
        "code": code_record.code,
        "user_name": user.get_full_name() or user.username,
        "logo_cid": "nuboxed-logo",
        "has_logo": bool(logo_field),
    })
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=mail_config.get("default_from_email") or settings.DEFAULT_FROM_EMAIL,
        to=[recipient_email or user.email],
        connection=connection,
    )
    message.attach_alternative(html_body, "text/html")
    if logo_field:
        try:
            logo_image = _email_logo_image(logo_field)
            logo_image.add_header("Content-ID", "<nuboxed-logo>")
            logo_image.add_header("Content-Disposition", "inline", filename="nuboxed-logo")
            message.attach(logo_image)
        except (OSError, ValueError):
            # Keep the branded text email working if the optional logo file is unavailable.
            pass
    sent = message.send(fail_silently=False)
    if sent != 1:
        raise RuntimeError("The verification email could not be sent.")
    return code_record
