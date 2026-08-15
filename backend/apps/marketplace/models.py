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


class MarketplaceListing(BaseModel):
    """Stable SKU mapping between a local sellable item and a marketplace."""
    connection = models.ForeignKey(MarketplaceConnection, related_name="listings", on_delete=models.CASCADE)
    product = models.ForeignKey("catalog.Product", related_name="marketplace_listings", on_delete=models.CASCADE)
    variant = models.ForeignKey("catalog.ProductVariant", related_name="marketplace_listings", null=True, blank=True, on_delete=models.CASCADE)
    seller_sku = models.CharField(max_length=120)
    external_listing_id = models.CharField(max_length=255, blank=True)
    marketplace_id = models.CharField(max_length=80, blank=True)
    fulfillment_location = models.ForeignKey("inventory.Warehouse", related_name="marketplace_listings", null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=32, default="pending")
    last_pushed_quantity = models.IntegerField(null=True, blank=True)
    last_pushed_at = models.DateTimeField(null=True, blank=True)
    last_pulled_quantity = models.IntegerField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        # One Nuboxed variant can have several Amazon offer SKUs (for
        # example condition A/B/C offers for the same colour/storage child).
        # Seller SKU remains unique per Amazon connection.
        unique_together = (("connection", "seller_sku"),)
        ordering = ("seller_sku",)

    def __str__(self):
        return f"{self.connection.name} / {self.seller_sku}"


class MarketplaceStoreMapping(BaseModel):
    """Maps each Nuboxed store under a retailer seller connection."""
    connection = models.ForeignKey(MarketplaceConnection, related_name="store_mappings", on_delete=models.CASCADE)
    store = models.ForeignKey("stores.Store", related_name="marketplace_store_mappings", on_delete=models.CASCADE)
    warehouse = models.ForeignKey("inventory.Warehouse", related_name="marketplace_store_mappings", null=True, blank=True, on_delete=models.SET_NULL)
    amazon_store_code = models.CharField(max_length=120, blank=True)
    is_enabled = models.BooleanField(default=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        unique_together = (("connection", "store"),)
        ordering = ("store__name",)

    def __str__(self):
        return f"{self.connection.name} / {self.store.name}"


class AmazonOrderTracking(BaseModel):
    """Auditable Amazon order record, independent of local order creation."""
    connection = models.ForeignKey(MarketplaceConnection, related_name="amazon_orders", on_delete=models.CASCADE)
    retailer = models.ForeignKey("retailers.Retailer", related_name="amazon_order_tracking", null=True, blank=True, on_delete=models.SET_NULL)
    store = models.ForeignKey("stores.Store", related_name="amazon_order_tracking", null=True, blank=True, on_delete=models.SET_NULL)
    local_order = models.ForeignKey("orders.Order", related_name="amazon_tracking_records", null=True, blank=True, on_delete=models.SET_NULL)
    external_order_id = models.CharField(max_length=120)
    amazon_order_status = models.CharField(max_length=64, blank=True)
    fulfillment_status = models.CharField(max_length=64, blank=True)
    attribution_status = models.CharField(max_length=32, default="pending")
    marketplace_id = models.CharField(max_length=80, blank=True)
    purchase_date = models.DateTimeField(null=True, blank=True)
    order_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency_code = models.CharField(max_length=3, blank=True)
    shipping_city = models.CharField(max_length=120, blank=True)
    shipping_country_code = models.CharField(max_length=2, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    imported_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = (("connection", "external_order_id"),)
        ordering = ("-purchase_date", "-created_at")
        indexes = [models.Index(fields=["retailer", "amazon_order_status"]), models.Index(fields=["store", "purchase_date"])]

    def __str__(self):
        return self.external_order_id


class AmazonOrderItemTracking(BaseModel):
    tracking_order = models.ForeignKey(AmazonOrderTracking, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey("catalog.Product", related_name="amazon_order_items", null=True, blank=True, on_delete=models.SET_NULL)
    variant = models.ForeignKey("catalog.ProductVariant", related_name="amazon_order_items", null=True, blank=True, on_delete=models.SET_NULL)
    retailer = models.ForeignKey("retailers.Retailer", related_name="amazon_order_items", null=True, blank=True, on_delete=models.SET_NULL)
    store = models.ForeignKey("stores.Store", related_name="amazon_order_items", null=True, blank=True, on_delete=models.SET_NULL)
    seller_sku = models.CharField(max_length=120, blank=True)
    title = models.CharField(max_length=255, blank=True)
    quantity = models.PositiveIntegerField(default=0)
    item_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
