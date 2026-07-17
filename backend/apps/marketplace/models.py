from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.common.models import BaseModel


class MarketplaceSetting(BaseModel):
    key = models.CharField(max_length=120, unique=True)
    value = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return self.key


class MarketplaceConnector(BaseModel):
    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_DRAFT = "draft"

    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    connector_type = models.CharField(max_length=64)
    status = models.CharField(max_length=32, default=STATUS_DRAFT)
    config = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return self.name


class MarketplaceConnection(BaseModel):
    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_ERROR = "error"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_INACTIVE, "Inactive"),
        (STATUS_ERROR, "Error"),
    ]

    connector = models.ForeignKey(MarketplaceConnector, related_name="connections", on_delete=models.CASCADE)
    retailer = models.ForeignKey("retailers.Retailer", related_name="marketplace_connections", null=True, blank=True, on_delete=models.CASCADE)
    store = models.ForeignKey("stores.Store", related_name="marketplace_connections", null=True, blank=True, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_INACTIVE)
    
    credentials = models.JSONField(default=dict, blank=True)
    access_token = models.TextField(blank=True)
    refresh_token = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    
    last_sync_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"{self.connector.name} - {self.name}"


class MarketplaceSyncJob(BaseModel):
    TYPE_PRODUCT_SYNC = "product_sync"
    TYPE_PRICE_SYNC = "price_sync"
    TYPE_STOCK_SYNC = "stock_sync"
    TYPE_ORDER_IMPORT = "order_import"
    TYPE_RETURN_SYNC = "return_sync"
    TYPE_REFUND_SYNC = "refund_sync"
    TYPE_SETTLEMENT_SYNC = "settlement_sync"

    TYPE_CHOICES = [
        (TYPE_PRODUCT_SYNC, "Product Sync"),
        (TYPE_PRICE_SYNC, "Price Sync"),
        (TYPE_STOCK_SYNC, "Stock Sync"),
        (TYPE_ORDER_IMPORT, "Order Import"),
        (TYPE_RETURN_SYNC, "Return Sync"),
        (TYPE_REFUND_SYNC, "Refund Sync"),
        (TYPE_SETTLEMENT_SYNC, "Settlement Sync"),
    ]

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    DIRECTION_INBOUND = "inbound"
    DIRECTION_OUTBOUND = "outbound"

    DIRECTION_CHOICES = [
        (DIRECTION_INBOUND, "Inbound (Marketplace to CommerceOS)"),
        (DIRECTION_OUTBOUND, "Outbound (CommerceOS to Marketplace)"),
    ]

    connection = models.ForeignKey(MarketplaceConnection, related_name="sync_jobs", on_delete=models.CASCADE)
    job_type = models.CharField(max_length=64, choices=TYPE_CHOICES)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING)
    direction = models.CharField(max_length=32, choices=DIRECTION_CHOICES)
    
    payload = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    run_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return f"{self.job_type} ({self.status}) - Connection: {self.connection.name}"


class MarketplaceConflictLog(BaseModel):
    STRATEGY_LOCAL = "use_local"
    STRATEGY_EXTERNAL = "use_external"
    STRATEGY_MANUAL = "manual"

    STRATEGY_CHOICES = [
        (STRATEGY_LOCAL, "Use Local Data"),
        (STRATEGY_EXTERNAL, "Use External Data"),
        (STRATEGY_MANUAL, "Manual Resolution"),
    ]

    connection = models.ForeignKey(MarketplaceConnection, related_name="conflict_logs", on_delete=models.CASCADE)
    entity_type = models.CharField(max_length=64)  # e.g., product, price, stock, order
    entity_id = models.CharField(max_length=255)   # Local entity ID
    external_id = models.CharField(max_length=255) # External entity ID
    
    local_data = models.JSONField(default=dict, blank=True)
    external_data = models.JSONField(default=dict, blank=True)
    conflict_reason = models.TextField(blank=True)
    
    resolution_strategy = models.CharField(max_length=32, choices=STRATEGY_CHOICES, default=STRATEGY_MANUAL)
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self) -> str:
        return f"Conflict on {self.entity_type} ({self.entity_id}) - Connection: {self.connection.name}"


class MarketplaceWebhookEvent(BaseModel):
    STATUS_PENDING = "pending"
    STATUS_PROCESSED = "processed"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSED, "Processed"),
        (STATUS_FAILED, "Failed"),
    ]

    connector_code = models.CharField(max_length=64)
    headers = models.JSONField(default=dict, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"Webhook event ({self.connector_code}) - Status: {self.status}"
