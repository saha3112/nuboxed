from rest_framework import serializers
from apps.marketplace.models import (
    MarketplaceConnector,
    MarketplaceConnection,
    MarketplaceSyncJob,
    MarketplaceConflictLog,
    MarketplaceWebhookEvent
)


class MarketplaceConnectorSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketplaceConnector
        fields = ["id", "code", "name", "connector_type", "status", "config", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class MarketplaceConnectionSerializer(serializers.ModelSerializer):
    connector_name = serializers.CharField(source="connector.name", read_only=True)
    connector_code = serializers.CharField(source="connector.code", read_only=True)
    retailer_name = serializers.CharField(source="retailer.legal_name", read_only=True, default=None)

    class Meta:
        model = MarketplaceConnection
        fields = [
            "id", "connector", "connector_name", "connector_code", "retailer", "retailer_name",
            "store", "name", "status", "credentials", "access_token", "refresh_token",
            "token_expires_at", "last_sync_at", "error_message", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "status", "access_token", "refresh_token", "token_expires_at", "last_sync_at", "error_message", "created_at", "updated_at"]


class MarketplaceConnectionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketplaceConnection
        fields = ["connector", "retailer", "store", "name", "credentials"]


class MarketplaceSyncJobSerializer(serializers.ModelSerializer):
    connection_name = serializers.CharField(source="connection.name", read_only=True)
    connector_code = serializers.CharField(source="connection.connector.code", read_only=True)

    class Meta:
        model = MarketplaceSyncJob
        fields = [
            "id", "connection", "connection_name", "connector_code", "job_type", "status",
            "direction", "payload", "result", "error_message", "retry_count", "max_retries",
            "run_at", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class MarketplaceConflictLogSerializer(serializers.ModelSerializer):
    connection_name = serializers.CharField(source="connection.name", read_only=True)
    resolved_by_email = serializers.EmailField(source="resolved_by.email", read_only=True, default=None)

    class Meta:
        model = MarketplaceConflictLog
        fields = [
            "id", "connection", "connection_name", "entity_type", "entity_id", "external_id",
            "local_data", "external_data", "conflict_reason", "resolution_strategy",
            "is_resolved", "resolved_at", "resolved_by", "resolved_by_email", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "is_resolved", "resolved_at", "resolved_by", "created_at", "updated_at"]


class ResolveConflictInputSerializer(serializers.Serializer):
    resolution_strategy = serializers.ChoiceField(choices=[("use_local", "Use Local"), ("use_external", "Use External"), ("manual", "Manual")])


class MarketplaceWebhookEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketplaceWebhookEvent
        fields = ["id", "connector_code", "headers", "payload", "status", "processed_at", "error_message", "created_at", "updated_at"]
        read_only_fields = ["id", "status", "processed_at", "error_message", "created_at", "updated_at"]
