from django.contrib import admin
from apps.marketplace.models import (
    MarketplaceSetting,
    MarketplaceConnector,
    MarketplaceConnection,
    MarketplaceSyncJob,
    MarketplaceConflictLog,
    MarketplaceWebhookEvent
    , MarketplaceListing, MarketplaceStoreMapping, AmazonOrderTracking, AmazonOrderItemTracking
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


@admin.register(MarketplaceListing)
class MarketplaceListingAdmin(admin.ModelAdmin):
    list_display = ("seller_sku", "connection", "product", "fulfillment_location", "status", "last_pushed_at")
    list_filter = ("status", "connection")
    search_fields = ("seller_sku", "product__name", "product__sku")


@admin.register(MarketplaceStoreMapping)
class MarketplaceStoreMappingAdmin(admin.ModelAdmin):
    list_display = ("connection", "store", "warehouse", "amazon_store_code", "is_enabled", "last_sync_at")
    list_filter = ("is_enabled", "connection")
    search_fields = ("store__name", "amazon_store_code", "warehouse__name")


@admin.register(AmazonOrderTracking)
class AmazonOrderTrackingAdmin(admin.ModelAdmin):
    list_display = ("external_order_id", "retailer", "store", "amazon_order_status", "fulfillment_status", "purchase_date", "local_order")
    list_filter = ("amazon_order_status", "fulfillment_status", "attribution_status", "marketplace_id")
    search_fields = ("external_order_id", "retailer__legal_name", "retailer__display_name", "store__name")


@admin.register(AmazonOrderItemTracking)
class AmazonOrderItemTrackingAdmin(admin.ModelAdmin):
    list_display = ("tracking_order", "seller_sku", "retailer", "store", "quantity", "item_total")
    search_fields = ("seller_sku", "title", "tracking_order__external_order_id")
