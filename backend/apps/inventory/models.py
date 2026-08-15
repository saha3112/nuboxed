from django.db import models

from apps.common.models import BaseModel


class Warehouse(BaseModel):
    retailer = models.ForeignKey("retailers.Retailer", related_name="warehouses", on_delete=models.CASCADE)
    store = models.ForeignKey(
        "stores.Store",
        related_name="warehouses",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=32, blank=True)
    country_code = models.CharField(max_length=2, default="DE")
    delivery_days = models.PositiveIntegerField(default=3)
    handling_time_days = models.PositiveIntegerField(default=1)
    is_default = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.name


class StockItem(BaseModel):
    product = models.ForeignKey("catalog.Product", related_name="stock_items", on_delete=models.CASCADE)
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        related_name="stock_items",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    warehouse = models.ForeignKey(Warehouse, related_name="stock_items", on_delete=models.CASCADE)
    on_hand_quantity = models.IntegerField(default=0)
    reserved_quantity = models.IntegerField(default=0)
    damaged_quantity = models.IntegerField(default=0)
    returned_quantity = models.IntegerField(default=0)
    low_stock_threshold = models.IntegerField(default=0)

    class Meta:
        unique_together = ("product", "variant", "warehouse")

    @property
    def available_quantity(self):
        return self.on_hand_quantity - self.reserved_quantity

    @property
    def is_low_stock(self):
        return self.available_quantity <= self.low_stock_threshold


class StockLedger(BaseModel):
    TYPE_MANUAL_ADJUSTMENT = "manual_adjustment"
    TYPE_RESERVATION = "reservation"
    TYPE_RESERVATION_RELEASE = "reservation_release"
    TYPE_ONLINE_SALE = "online_sale"
    TYPE_CANCEL_RESTORE = "cancel_restore"
    TYPE_OFFLINE_SALE = "offline_sale"
    TYPE_DAMAGE = "damage"
    TYPE_RETURN_PENDING = "return_pending"
    TYPE_RETURN_RESTOCK = "return_restock"
    TYPE_QC_REJECT = "qc_reject"

    TYPE_CHOICES = [
        (TYPE_MANUAL_ADJUSTMENT, "Manual adjustment"),
        (TYPE_RESERVATION, "Reservation"),
        (TYPE_RESERVATION_RELEASE, "Reservation release"),
        (TYPE_ONLINE_SALE, "Online sale"),
        (TYPE_CANCEL_RESTORE, "Cancelled order restore"),
        (TYPE_OFFLINE_SALE, "Offline sale"),
        (TYPE_DAMAGE, "Damaged stock"),
        (TYPE_RETURN_PENDING, "Returned stock pending QC"),
        (TYPE_RETURN_RESTOCK, "Returned stock restocked"),
        (TYPE_QC_REJECT, "QC rejected return"),
    ]

    warehouse = models.ForeignKey(Warehouse, related_name="ledger_entries", on_delete=models.CASCADE)
    stock_item = models.ForeignKey(StockItem, related_name="ledger_entries", on_delete=models.CASCADE)
    product = models.ForeignKey("catalog.Product", related_name="stock_ledger_entries", on_delete=models.CASCADE)
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        related_name="stock_ledger_entries",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    movement_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    quantity_delta = models.IntegerField()
    reference_type = models.CharField(max_length=64, blank=True)
    reference_id = models.CharField(max_length=64, blank=True)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "users.User",
        related_name="created_stock_ledger_entries",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    def __str__(self):
        return f"{self.product} / {self.movement_type} / {self.quantity_delta}"


class StockReservation(BaseModel):
    STATUS_RESERVED = "reserved"
    STATUS_RELEASED = "released"
    STATUS_CONSUMED = "consumed"
    STATUS_RESTORED = "restored"

    STATUS_CHOICES = [
        (STATUS_RESERVED, "Reserved"),
        (STATUS_RELEASED, "Released"),
        (STATUS_CONSUMED, "Consumed"),
        (STATUS_RESTORED, "Restored"),
    ]

    warehouse = models.ForeignKey(Warehouse, related_name="stock_reservations", on_delete=models.CASCADE)
    stock_item = models.ForeignKey(StockItem, related_name="reservations", on_delete=models.CASCADE)
    product = models.ForeignKey("catalog.Product", related_name="stock_reservations", on_delete=models.CASCADE)
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        related_name="stock_reservations",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    order = models.ForeignKey(
        "orders.Order",
        related_name="stock_reservations",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    order_item = models.ForeignKey(
        "orders.OrderItem",
        related_name="stock_reservations",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    quantity = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RESERVED)


class OfflineSale(BaseModel):
    warehouse = models.ForeignKey(Warehouse, related_name="offline_sales", on_delete=models.CASCADE)
    store = models.ForeignKey("stores.Store", related_name="offline_sales", on_delete=models.CASCADE)
    delivery_location = models.ForeignKey(
        "inventory.DeliveryLocation",
        related_name="offline_sales",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    selected_pincode = models.CharField(max_length=32, blank=True)
    product = models.ForeignKey("catalog.Product", related_name="offline_sales", on_delete=models.CASCADE)
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        related_name="offline_sales",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sold_at = models.DateTimeField()
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "users.User",
        related_name="created_offline_sales",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )


class StockAdjustment(BaseModel):
    TYPE_INCREASE = "increase"
    TYPE_DECREASE = "decrease"
    TYPE_DAMAGE = "damage"

    TYPE_CHOICES = [
        (TYPE_INCREASE, "Increase"),
        (TYPE_DECREASE, "Decrease"),
        (TYPE_DAMAGE, "Damage"),
    ]

    warehouse = models.ForeignKey(Warehouse, related_name="stock_adjustments", on_delete=models.CASCADE)
    product = models.ForeignKey("catalog.Product", related_name="stock_adjustments", on_delete=models.CASCADE)
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        related_name="stock_adjustments",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    quantity = models.IntegerField()
    adjustment_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "users.User",
        related_name="created_stock_adjustments",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )


class LowStockAlert(BaseModel):
    stock_item = models.ForeignKey(StockItem, related_name="low_stock_alerts", on_delete=models.CASCADE)
    triggered_quantity = models.IntegerField()
    resolved_at = models.DateTimeField(null=True, blank=True)


class DeliveryLocation(BaseModel):
    retailer = models.ForeignKey("retailers.Retailer", related_name="delivery_locations", on_delete=models.CASCADE)
    store = models.ForeignKey(
        "stores.Store",
        related_name="delivery_locations",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    warehouse = models.ForeignKey(
        Warehouse,
        related_name="delivery_locations",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=255)
    postal_code = models.CharField(max_length=255, blank=True)
    postal_code_prefix = models.CharField(max_length=255, blank=True)
    pin_details = models.JSONField(default=dict, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True)
    country_code = models.CharField(max_length=2, default="DE")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    service_radius_km = models.PositiveIntegerField(default=0)
    delivery_days = models.PositiveIntegerField(default=3)
    handling_time_days = models.PositiveIntegerField(default=0)
    priority = models.PositiveIntegerField(default=100)

    class Meta:
        ordering = ("priority", "name")
        indexes = [
            models.Index(fields=["retailer", "postal_code"]),
            models.Index(fields=["retailer", "postal_code_prefix"]),
            models.Index(fields=["store", "warehouse"]),
        ]

    def __str__(self) -> str:
        return self.name


class CategoryDeliveryRule(BaseModel):
    retailer = models.ForeignKey(
        "retailers.Retailer",
        related_name="category_delivery_rules",
        on_delete=models.CASCADE,
    )
    store = models.ForeignKey(
        "stores.Store",
        related_name="category_delivery_rules",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    category = models.ForeignKey(
        "catalog.Category",
        related_name="delivery_rules",
        on_delete=models.CASCADE,
    )
    delivery_days = models.PositiveIntegerField(default=3)

    class Meta:
        unique_together = ("retailer", "store", "category")

    def __str__(self) -> str:
        return f"{self.category} / {self.delivery_days} days"


class ProductDeliveryRule(BaseModel):
    retailer = models.ForeignKey(
        "retailers.Retailer",
        related_name="product_delivery_rules",
        on_delete=models.CASCADE,
    )
    product = models.ForeignKey(
        "catalog.Product",
        related_name="delivery_rules",
        on_delete=models.CASCADE,
    )
    warehouse = models.ForeignKey(
        Warehouse,
        related_name="product_delivery_rules",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    delivery_days = models.PositiveIntegerField(default=3)

    class Meta:
        unique_together = ("retailer", "product", "warehouse")

    def __str__(self) -> str:
        return f"{self.product} / {self.delivery_days} days"
