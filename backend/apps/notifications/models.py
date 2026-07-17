from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.common.models import BaseModel


class NotificationTemplate(BaseModel):
    CHANNEL_EMAIL = "email"
    CHANNEL_SMS = "sms"
    CHANNEL_WHATSAPP = "whatsapp"
    CHANNEL_PUSH = "push"
    CHANNEL_IN_APP = "in_app"

    CHANNEL_CHOICES = [
        (CHANNEL_EMAIL, "Email"),
        (CHANNEL_SMS, "SMS"),
        (CHANNEL_WHATSAPP, "WhatsApp"),
        (CHANNEL_PUSH, "Push Notification"),
        (CHANNEL_IN_APP, "In-App Notification"),
    ]

    event_name = models.CharField(max_length=64)  # e.g., new_order, low_stock
    channel = models.CharField(max_length=32, choices=CHANNEL_CHOICES)
    subject_template = models.CharField(max_length=255, blank=True)
    body_template = models.TextField()

    class Meta:
        unique_together = ("event_name", "channel")

    def __str__(self) -> str:
        return f"{self.event_name} - {self.channel}"


class Notification(BaseModel):
    STATUS_PENDING = "pending"
    STATUS_QUEUED = "queued"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_QUEUED, "Queued"),
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="notifications",
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    recipient = models.CharField(max_length=255, blank=True)  # Email address, phone number, or push token
    channel = models.CharField(max_length=32)
    event_name = models.CharField(max_length=64, blank=True)
    
    subject = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING)
    
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    error_message = models.TextField(blank=True)
    run_at = models.DateTimeField(default=timezone.now)
    
    read_at = models.DateTimeField(null=True, blank=True)  # Used for in-app/push notifications

    def __str__(self) -> str:
        return f"{self.subject} ({self.channel}) - {self.status}"


class NotificationDeliveryLog(BaseModel):
    notification = models.ForeignKey(Notification, related_name="delivery_logs", on_delete=models.CASCADE)
    status = models.CharField(max_length=32)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Log for Notification {self.notification.id} - Status: {self.status}"
