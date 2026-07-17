from rest_framework import serializers
from apps.notifications.models import NotificationTemplate, Notification, NotificationDeliveryLog


class NotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplate
        fields = ["id", "event_name", "channel", "subject_template", "body_template", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class NotificationDeliveryLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationDeliveryLog
        fields = ["id", "status", "error_message", "sent_at"]


class NotificationSerializer(serializers.ModelSerializer):
    delivery_logs = NotificationDeliveryLogSerializer(many=True, read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True, default=None)

    class Meta:
        model = Notification
        fields = [
            "id", "user", "user_email", "recipient", "channel", "event_name",
            "subject", "body", "status", "retry_count", "max_retries", "error_message",
            "run_at", "read_at", "delivery_logs", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "status", "retry_count", "error_message", "run_at", "created_at", "updated_at"]


class SendNotificationEventSerializer(serializers.Serializer):
    event_name = serializers.CharField(max_length=64)
    context = serializers.JSONField(default=dict)
    recipient = serializers.CharField(required=False, allow_blank=True, default="")
