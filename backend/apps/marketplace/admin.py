from django.contrib import admin
from apps.marketplace.models import (
    MarketplaceSetting,
    MarketplaceConnector,
    MarketplaceConnection,
    MarketplaceSyncJob,
    MarketplaceConflictLog,
    MarketplaceWebhookEvent
)


@admin.register(MarketplaceSetting)
class MarketplaceSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "created_at")
    search_fields = ("key",)


@admin.register(MarketplaceConnector)
class MarketplaceConnectorAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "connector_type", "status", "is_active")
    list_filter = ("status", "connector_type", "is_active")
    search_fields = ("code", "name")


@admin.register(MarketplaceConnection)
class MarketplaceConnectionAdmin(admin.ModelAdmin):
    list_display = ("name", "connector", "retailer", "store", "status", "last_sync_at")
    list_filter = ("status", "connector", "last_sync_at")
    search_fields = ("name", "connector__name", "retailer__legal_name", "store__name")


class MarketplaceSyncJobInline(admin.TabularInline):
    model = MarketplaceSyncJob
    extra = 0
    readonly_fields = ("created_at", "updated_at")


@admin.register(MarketplaceSyncJob)
class MarketplaceSyncJobAdmin(admin.ModelAdmin):
    list_display = ("job_type", "connection", "status", "direction", "retry_count", "run_at", "created_at")
    list_filter = ("status", "job_type", "direction", "created_at")
    search_fields = ("connection__name", "error_message")


@admin.register(MarketplaceConflictLog)
class MarketplaceConflictLogAdmin(admin.ModelAdmin):
    list_display = ("entity_type", "connection", "entity_id", "external_id", "resolution_strategy", "is_resolved", "resolved_at")
    list_filter = ("is_resolved", "resolution_strategy", "entity_type")
    search_fields = ("entity_id", "external_id", "conflict_reason")


@admin.register(MarketplaceWebhookEvent)
class MarketplaceWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("connector_code", "status", "processed_at", "created_at")
    list_filter = ("status", "connector_code", "created_at")
    search_fields = ("connector_code", "error_message")
