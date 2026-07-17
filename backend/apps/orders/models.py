from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel


class Cart(BaseModel):
    STATUS_OPEN = "open"
    STATUS_CONVERTED = "converted"
    STATUS_ABANDONED = "abandoned"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_CONVERTED, "Converted"),
        (STATUS_ABANDONED, "Abandoned"),
    ]

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="carts",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    session_key = models.CharField(max_length=80, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    currency_code = models.CharField(max_length=3, default="EUR")
    coupon_code = models.CharField(max_length=64, blank=True)
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_postal_code = models.CharField(max_length=32, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self) -> str:
        return f"Cart {self.id}"


class CartItem(BaseModel):
    cart = models.ForeignKey(Cart, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey("catalog.Product", related_name="cart_items", on_delete=models.CASCADE)
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        related_name="cart_items",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    line_subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        unique_together = ("cart", "product", "variant")

    def __str__(self) -> str:
        return f"{self.product} x {self.quantity}"


class Order(BaseModel):
    STATUS_DRAFT = "draft"
    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_PROCESSING = "processing"
    STATUS_SHIPPED = "shipped"
    STATUS_DELIVERED = "delivered"
    STATUS_CANCELLED = "cancelled"

    PAYMENT_PENDING = "pending"
    PAYMENT_AUTHORIZED = "authorized"
    PAYMENT_PAID = "paid"
    PAYMENT_FAILED = "failed"

    SOURCE_WEBSITE = "website"
    SOURCE_AMAZON = "amazon"
    SOURCE_FLIPKART = "flipkart"
    SOURCE_EBAY = "ebay"
    SOURCE_SHOPIFY = "shopify"
    SOURCE_WOOCOMMERCE = "woocommerce"
    SOURCE_OFFLINE = "offline"

    FULFILLMENT_INTERNAL_COURIER = "internal_courier"
    FULFILLMENT_AMAZON = "amazon_fulfillment"
    FULFILLMENT_FLIPKART = "flipkart_fulfillment"
    FULFILLMENT_EBAY = "ebay_fulfillment"
    FULFILLMENT_PLATFORM = "platform_fulfillment"
    FULFILLMENT_OFFLINE = "offline_flow"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PENDING, "Pending"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_SHIPPED, "Shipped"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_CANCELLED, "Cancelled"),
    ]
    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_PENDING, "Pending"),
        (PAYMENT_AUTHORIZED, "Authorized"),
        (PAYMENT_PAID, "Paid"),
        (PAYMENT_FAILED, "Failed"),
    ]
    SOURCE_CHOICES = [
        (SOURCE_WEBSITE, "Website"),
        (SOURCE_AMAZON, "Amazon"),
        (SOURCE_FLIPKART, "Flipkart"),
        (SOURCE_EBAY, "eBay"),
        (SOURCE_SHOPIFY, "Shopify"),
        (SOURCE_WOOCOMMERCE, "WooCommerce"),
        (SOURCE_OFFLINE, "Offline"),
    ]
    FULFILLMENT_FLOW_CHOICES = [
        (FULFILLMENT_INTERNAL_COURIER, "Internal courier"),
        (FULFILLMENT_AMAZON, "Amazon fulfillment"),
        (FULFILLMENT_FLIPKART, "Flipkart fulfillment"),
        (FULFILLMENT_EBAY, "eBay fulfillment"),
        (FULFILLMENT_PLATFORM, "Platform fulfillment"),
        (FULFILLMENT_OFFLINE, "Offline flow"),
    ]

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="orders",
        on_delete=models.PROTECT,
    )
    retailer = models.ForeignKey("retailers.Retailer", related_name="orders", on_delete=models.PROTECT)
    marketplace_connector = models.ForeignKey(
        "marketplace.MarketplaceConnector",
        related_name="orders",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    cart = models.ForeignKey(
        Cart,
        related_name="orders",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    number = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default=PAYMENT_PENDING,
    )
    source_channel = models.CharField(
        max_length=32,
        choices=SOURCE_CHOICES,
        default=SOURCE_WEBSITE,
    )
    external_order_reference = models.CharField(max_length=120, blank=True)
    external_customer_reference = models.CharField(max_length=120, blank=True)
    fulfillment_flow = models.CharField(
        max_length=32,
        choices=FULFILLMENT_FLOW_CHOICES,
        default=FULFILLMENT_INTERNAL_COURIER,
    )
    currency_code = models.CharField(max_length=3, default="EUR")
    address = models.ForeignKey(
        "users.UserAddress",
        related_name="orders",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    shipping_full_name = models.CharField(max_length=255, blank=True)
    shipping_phone = models.CharField(max_length=32, blank=True)
    shipping_address_line1 = models.CharField(max_length=255, blank=True)
    shipping_address_line2 = models.CharField(max_length=255, blank=True)
    shipping_city = models.CharField(max_length=120, blank=True)
    shipping_state = models.CharField(max_length=120, blank=True)
    shipping_postal_code = models.CharField(max_length=32, blank=True)
    shipping_country_code = models.CharField(max_length=2, default="DE")
    delivery_estimate_date = models.DateField(null=True, blank=True)
    shipping_method = models.CharField(max_length=64, default=FULFILLMENT_INTERNAL_COURIER)
    payment_method = models.CharField(max_length=64, blank=True)
    coupon_code = models.CharField(max_length=64, blank=True)
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock_deducted_at = models.DateTimeField(null=True, blank=True)
    stock_restored_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    placed_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.number

    @property
    def is_website_order(self):
        return self.source_channel == self.SOURCE_WEBSITE

    @property
    def is_external_marketplace_order(self):
        return self.source_channel in {
            self.SOURCE_AMAZON,
            self.SOURCE_FLIPKART,
            self.SOURCE_EBAY,
            self.SOURCE_SHOPIFY,
            self.SOURCE_WOOCOMMERCE,
        }

    @property
    def requires_internal_courier_booking(self):
        return self.fulfillment_flow == self.FULFILLMENT_INTERNAL_COURIER and self.is_website_order

    def mark_confirmed(self):
        self.status = self.STATUS_CONFIRMED
        self.confirmed_at = timezone.now()
        self.save(update_fields=["status", "confirmed_at", "updated_at"])


class OrderItem(BaseModel):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey("catalog.Product", related_name="order_items", on_delete=models.PROTECT)
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        related_name="order_items",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    warehouse = models.ForeignKey(
        "inventory.Warehouse",
        related_name="order_items",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_estimate_date = models.DateField(null=True, blank=True)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)


class OrderTimeline(BaseModel):
    order = models.ForeignKey(Order, related_name="timeline_entries", on_delete=models.CASCADE)
    status = models.CharField(max_length=32)
    title = models.CharField(max_length=255)
    note = models.TextField(blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="order_timeline_entries",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    class Meta:
        ordering = ("occurred_at", "created_at")

    def __str__(self) -> str:
        return f"{self.order.number} / {self.status}"


class OrderWorkflowSetting(BaseModel):
    """Retailer-owned operational switches for the shared order workflow."""
    retailer = models.OneToOneField("retailers.Retailer", related_name="order_workflow_setting", on_delete=models.CASCADE)
    auto_invoice = models.BooleanField(default=True)
    allow_manual_invoice = models.BooleanField(default=True)
    auto_label = models.BooleanField(default=True)
    allow_manual_label = models.BooleanField(default=True)
    notify_customer_order_placed = models.BooleanField(default=True)
    notify_customer_status_changed = models.BooleanField(default=True)

    def __str__(self):
        return f"Order workflow — {self.retailer}"


class DeliveryLabel(BaseModel):
    """Printable packing label generated from the immutable order snapshot."""
    STATUS_GENERATED = "generated"
    STATUS_PRINTED = "printed"
    STATUS_CHOICES = ((STATUS_GENERATED, "Generated"), (STATUS_PRINTED, "Printed"))
    order = models.OneToOneField(Order, related_name="delivery_label", on_delete=models.CASCADE)
    label_number = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_GENERATED)
    payload = models.JSONField(default=dict, blank=True)
    generated_at = models.DateTimeField(default=timezone.now)
    printed_at = models.DateTimeField(null=True, blank=True)
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
