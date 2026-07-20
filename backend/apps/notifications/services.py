import logging
import re
from typing import Dict, Any, List
from django.db import transaction
from django.utils import timezone
from django.core.mail import get_connection, send_mail

from apps.notifications.models import NotificationTemplate, Notification, NotificationDeliveryLog
from apps.settings_app.models import BrandSettings, Setting

logger = logging.getLogger(__name__)


def render_template(template_str: str, context: Dict[str, Any]) -> str:
    """
    Renders simple double-brace templates, e.g., {{ order_number }} with context.
    """
    if not template_str:
        return ""
    
    def replacement(match):
        key = match.group(1).strip()
        val = context.get(key, "")
        return str(val)

    return re.sub(r"\{\{\s*([^}]+)\s*\}\}", replacement, template_str)


@transaction.atomic
def create_notification_template(event_name: str, channel: str, subject_template: str, body_template: str) -> NotificationTemplate:
    """
    Creates or updates a notification template for an event + channel combo.
    """
    template, created = NotificationTemplate.objects.update_or_create(
        event_name=event_name,
        channel=channel,
        defaults={
            "subject_template": subject_template,
            "body_template": body_template,
        }
    )
    return template


@transaction.atomic
def send_notification_event(event_name: str, context: Dict[str, Any], user=None, recipient: str = None, extra_recipients=None) -> List[Notification]:
    """
    Dispatches notifications across all configured channels for a triggered event.
    Renders templates and enqueues individual Notification records.
    """
    brand = BrandSettings.objects.filter(is_active=True).first()
    brand_name = (brand.brand_name or "Nuboxed") if brand else "Nuboxed"
    context = {**context, "brand_name": brand_name}
    templates = NotificationTemplate.objects.filter(event_name=event_name, is_active=True)
    created_notifications = []
    extra_recipients = [email for email in (extra_recipients or []) if email]

    # If no templates exist, create a default in-app/email notification so the system functions
    if not templates.exists():
        subject = {
            "new_order": f"Order {context.get('order_number', '')} placed successfully",
            "order_status_changed": f"Order {context.get('order_number', '')} status updated",
            "user_registered": f"Welcome to {brand_name} — your account is ready",
            "retailer_registered": "A new retailer has registered",
            "return_request": f"Return request {context.get('return_number', '')} received",
        }.get(event_name, f"Event triggered: {event_name.replace('_', ' ').title()}")
        body = {
            "new_order": f"Your order {context.get('order_number', '')} was placed successfully. Total: {context.get('amount', '')}.",
            "order_status_changed": f"Your order {context.get('order_number', '')} is now {context.get('status', '')}.",
            "user_registered": f"Welcome to {brand_name}, {context.get('name', '')}. Your account was created successfully.",
            "retailer_registered": f"Retailer {context.get('legal_name', '')} has been added.",
            "return_request": f"Return request {context.get('return_number', '')} has been placed.",
        }.get(event_name, f"An event of type '{event_name}' occurred. Context details: {str(context)}")
        
        # Email fallback
        targets = list(dict.fromkeys([recipient or (user.email if user else "")] + extra_recipients))
        for target in targets:
            n = Notification.objects.create(
            user=user if target == (user.email if user else "") else None,
            recipient=target,
            channel="email",
            event_name=event_name,
            subject=subject,
            body=body,
            status=Notification.STATUS_PENDING
            )
            created_notifications.append(n)
        
        # In-app fallback
        n_inapp = Notification.objects.create(
            user=user,
            recipient="",
            channel="in_app",
            event_name=event_name,
            subject=subject,
            body=body,
            status=Notification.STATUS_PENDING
        )
        created_notifications.append(n_inapp)
    else:
        for t in templates:
            subject = render_template(t.subject_template, context).replace("CommerceOS", brand_name)
            body = render_template(t.body_template, context).replace("CommerceOS", brand_name)
            
            # Resolve recipient based on channel
            target_recipient = recipient or ""
            if not target_recipient and user:
                if t.channel == NotificationTemplate.CHANNEL_EMAIL:
                    target_recipient = user.email
                elif t.channel in [NotificationTemplate.CHANNEL_SMS, NotificationTemplate.CHANNEL_WHATSAPP]:
                    target_recipient = getattr(user, "phone_number", "")
                elif t.channel == NotificationTemplate.CHANNEL_PUSH:
                    target_recipient = getattr(user, "push_token", "")

            targets = [target_recipient] if t.channel == NotificationTemplate.CHANNEL_IN_APP else list(dict.fromkeys([target_recipient] + extra_recipients))
            for target in targets:
                n = Notification.objects.create(
                user=user if t.channel == NotificationTemplate.CHANNEL_IN_APP else (user if target == target_recipient else None),
                recipient=target,
                channel=t.channel,
                event_name=event_name,
                subject=subject,
                body=body,
                status=Notification.STATUS_PENDING
                )
                created_notifications.append(n)

    # Immediately trigger delivery process
    for n in created_notifications:
        dispatch_notification(n)

    return created_notifications


def dispatch_notification(notification: Notification) -> Notification:
    """
    Simulates sending the notification over mock gateways.
    Increments retry counters and writes delivery logs on failure.
    """
    notification.status = Notification.STATUS_QUEUED
    notification.save(update_fields=["status", "updated_at"])

    try:
        # Mock external gateways (SES, Twilio, Firebase)
        channel = notification.channel.lower()
        if channel == "email":
            logger.info(f"Sending Email to {notification.recipient}: {notification.subject}")
            if notification.recipient:
                mail_config = Setting.objects.filter(key="email_settings", is_active=True).values_list("value", flat=True).first() or {}
                connection = None
                if mail_config.get("host"):
                    connection = get_connection(
                        backend="django.core.mail.backends.smtp.EmailBackend",
                        host=mail_config.get("host"),
                        port=mail_config.get("port") or 587,
                        username=mail_config.get("username") or None,
                        password=mail_config.get("password") or None,
                        use_tls=bool(mail_config.get("use_tls")),
                        use_ssl=bool(mail_config.get("use_ssl")),
                        timeout=mail_config.get("timeout") or 30,
                        fail_silently=False,
                    )
                send_mail(
                    notification.subject,
                    notification.body,
                    mail_config.get("default_from_email") or None,
                    [notification.recipient],
                    fail_silently=False,
                    connection=connection,
                )
        elif channel == "sms":
            logger.info(f"Sending SMS to {notification.recipient}: {notification.body}")
        elif channel == "whatsapp":
            logger.info(f"Sending WhatsApp message to {notification.recipient}")
        elif channel == "push":
            logger.info(f"Pushing notification payload to token {notification.recipient}")
        elif channel == "in_app":
            logger.info(f"Adding in-app notification for User {notification.user_id if notification.user else 'System'}")
        else:
            raise ValueError(f"Unsupported channel provider: {channel}")

        # Simulate success
        notification.status = Notification.STATUS_SENT
        notification.save(update_fields=["status", "updated_at"])

        NotificationDeliveryLog.objects.create(
            notification=notification,
            status="success",
            error_message=""
        )

    except Exception as e:
        logger.exception(f"Delivery failed for notification {notification.id}")
        notification.status = Notification.STATUS_FAILED
        notification.error_message = str(e)
        notification.retry_count += 1
        notification.run_at = timezone.now() + timezone.timedelta(minutes=2 ** notification.retry_count)
        notification.save(update_fields=["status", "error_message", "retry_count", "run_at", "updated_at"])

        NotificationDeliveryLog.objects.create(
            notification=notification,
            status="failed",
            error_message=str(e)
        )

    return notification


def send_test_email(recipient: str, mail_config: Dict[str, Any], brand_name: str = "Nuboxed"):
    """Send a one-off SMTP test without creating a notification record."""
    connection = None
    if mail_config.get("host"):
        connection = get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=mail_config.get("host"),
            port=mail_config.get("port") or 587,
            username=mail_config.get("username") or None,
            password=mail_config.get("password") or None,
            use_tls=bool(mail_config.get("use_tls")),
            use_ssl=bool(mail_config.get("use_ssl")),
            timeout=mail_config.get("timeout") or 30,
            fail_silently=False,
        )
    send_mail(
        f"{brand_name} SMTP test email",
        f"This is a test email from {brand_name}. Your SMTP settings are working.",
        mail_config.get("default_from_email") or None,
        [recipient],
        fail_silently=False,
        connection=connection,
    )

def retry_failed_notifications() -> List[Notification]:
    """
    Discovers failed notifications ready for retry and processes them.
    """
    retried_notifications = []
    failed_items = Notification.objects.filter(
        status=Notification.STATUS_FAILED,
        retry_count__lt=models.F("max_retries"),
        run_at__lte=timezone.now()
    )

    for item in failed_items:
        retried_notifications.append(dispatch_notification(item))

    return retried_notifications


def seed_default_templates():
    """
    Utility to initialize templates for required system events.
    """
    events = [
        ("new_registration", "Welcome to {{ brand_name }}! Your account {{ email }} has been created."),
        ("retailer_approval", "Your retailer account {{ legal_name }} has been approved."),
        ("product_upload", "Product {{ product_name }} (SKU: {{ sku }}) has been uploaded."),
        ("product_moderation", "Product {{ product_name }} status updated to {{ status }}."),
        ("new_order", "Order {{ order_number }} has been placed. Total: {{ amount }} EUR."),
        ("payment_received", "Payment received for Order {{ order_number }}."),
        ("shipment_update", "Shipment update for Order {{ order_number }}: {{ tracking_status }}."),
        ("delivery_update", "Order {{ order_number }} has been delivered!"),
        ("return_request", "Return request {{ return_number }} has been filed."),
        ("refund_update", "Refund of {{ amount }} EUR completed for Return {{ return_number }}."),
        ("stock_low", "Low stock alert for SKU {{ sku }}: only {{ quantity }} items left."),
        ("offline_sale", "Offline sale of {{ amount }} EUR recorded."),
        ("marketplace_sync_error", "Sync error on connector {{ connector_code }}: {{ error }}."),
        ("courier_update", "Courier status update: {{ courier_status }}."),
    ]

    for event_name, body in events:
        # Create Email template
        create_notification_template(
            event_name=event_name,
            channel="email",
            subject_template=f"Notification: {event_name.replace('_', ' ').title()}",
            body_template=body
        )


def ensure_order_email_templates():
    """Create editable defaults once; never overwrite an administrator's copy."""
    defaults = {
        "user_registered": ("Welcome to {{ brand_name }}", "Welcome {{ name }}. Your {{ brand_name }} account was created successfully."),
        "new_registration": ("Welcome to {{ brand_name }}", "Your retailer account for {{ email }} has been created on {{ brand_name }}."),
        "new_order": ("Order {{ order_number }} placed successfully", "Your order {{ order_number }} was placed successfully. Total: {{ amount }}."),
        "order_status_changed": ("Order {{ order_number }} status updated", "Your order {{ order_number }} is now {{ status }}."),
        "return_request": ("Return request {{ return_number }} received", "Return request {{ return_number }} has been placed."),
        "refund_update": ("Refund update for {{ return_number }}", "Refund of {{ amount }} has been processed for return {{ return_number }}."),
    }
    for event_name, (subject, body) in defaults.items():
        NotificationTemplate.objects.get_or_create(event_name=event_name, channel=NotificationTemplate.CHANNEL_EMAIL, defaults={"subject_template": subject, "body_template": body})
