from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel


class Shipment(BaseModel):
    FLOW_INTERNAL_COURIER = "internal_courier"
    FLOW_AMAZON = "amazon_fulfillment"
    FLOW_FLIPKART = "flipkart_fulfillment"
    FLOW_EBAY = "ebay_fulfillment"
    FLOW_PLATFORM = "platform_fulfillment"
    FLOW_OFFLINE = "offline_flow"

    FLOW_CHOICES = [
        (FLOW_INTERNAL_COURIER, "Internal courier"),
        (FLOW_AMAZON, "Amazon fulfillment"),
        (FLOW_FLIPKART, "Flipkart fulfillment"),
        (FLOW_EBAY, "eBay fulfillment"),
        (FLOW_PLATFORM, "Platform fulfillment"),
        (FLOW_OFFLINE, "Offline flow"),
    ]

    order = models.ForeignKey("orders.Order", related_name="shipments", on_delete=models.CASCADE)
    courier_partner = models.ForeignKey(
        "shipments.CourierPartner",
        related_name="shipments",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    carrier = models.CharField(max_length=64)
    flow_type = models.CharField(max_length=32, choices=FLOW_CHOICES, default=FLOW_INTERNAL_COURIER)
    booking_source = models.CharField(max_length=32, default="system")
    external_shipment_reference = models.CharField(max_length=120, blank=True)
    tracking_number = models.CharField(max_length=120, unique=True)
    status = models.CharField(max_length=32, default="pending")
    tracking_status = models.CharField(max_length=64, blank=True)
    tracking_payload = models.JSONField(default=dict, blank=True)
    label_url = models.URLField(blank=True)
    label_payload = models.JSONField(default=dict, blank=True)
    pickup_reference = models.CharField(max_length=120, blank=True)
    pickup_scheduled_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    last_tracking_event_at = models.DateTimeField(null=True, blank=True)
    sync_only = models.BooleanField(default=False)
    settlement_sync_enabled = models.BooleanField(default=True)
    refund_sync_enabled = models.BooleanField(default=True)
    return_sync_enabled = models.BooleanField(default=True)
    report_sync_enabled = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.tracking_number


class CourierBooking(BaseModel):
    STATUS_PENDING = "pending"
    STATUS_BOOKED = "booked"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_BOOKED, "Booked"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    order = models.ForeignKey("orders.Order", related_name="courier_bookings", on_delete=models.CASCADE)
    shipment = models.OneToOneField(Shipment, related_name="courier_booking", on_delete=models.CASCADE)
    courier_partner = models.ForeignKey(
        "shipments.CourierPartner",
        related_name="courier_bookings",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    booking_reference = models.CharField(max_length=120, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    requested_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    label_url = models.URLField(blank=True)
    pickup_reference = models.CharField(max_length=120, blank=True)
    pickup_scheduled_at = models.DateTimeField(null=True, blank=True)
    pickup_payload = models.JSONField(default=dict, blank=True)
    delivery_webhook_payload = models.JSONField(default=dict, blank=True)
    tracking_payload = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return self.booking_reference


class CourierCredential(BaseModel):
    CREDENTIAL_API_KEY = "api_key"
    CREDENTIAL_API_SECRET = "api_secret"
    CREDENTIAL_WEBHOOK_SECRET = "webhook_secret"
    CREDENTIAL_PICKUP_TOKEN = "pickup_token"
    CREDENTIAL_BEARER = "bearer_token"

    CREDENTIAL_CHOICES = [
        (CREDENTIAL_API_KEY, "API key"),
        (CREDENTIAL_API_SECRET, "API secret"),
        (CREDENTIAL_WEBHOOK_SECRET, "Webhook secret"),
        (CREDENTIAL_PICKUP_TOKEN, "Pickup token"),
        (CREDENTIAL_BEARER, "Bearer token"),
    ]

    courier_partner = models.ForeignKey(
        "shipments.CourierPartner",
        related_name="credentials",
        on_delete=models.CASCADE,
    )
    credential_type = models.CharField(max_length=32, choices=CREDENTIAL_CHOICES)
    key_name = models.CharField(max_length=120, blank=True)
    value = models.TextField()
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ("courier_partner", "credential_type", "key_name")

    def __str__(self) -> str:
        return f"{self.courier_partner.name} / {self.credential_type}"


class CourierCountryServiceability(BaseModel):
    courier_partner = models.ForeignKey(
        "shipments.CourierPartner",
        related_name="country_serviceability",
        on_delete=models.CASCADE,
    )
    country_code = models.CharField(max_length=2)
    is_serviceable = models.BooleanField(default=True)
    min_transit_days = models.PositiveIntegerField(default=1)
    max_transit_days = models.PositiveIntegerField(default=5)
    cod_available = models.BooleanField(default=False)

    class Meta:
        unique_together = ("courier_partner", "country_code")

    def __str__(self) -> str:
        return f"{self.courier_partner.name} / {self.country_code}"


class CourierServiceabilityRule(BaseModel):
    courier_partner = models.ForeignKey(
        "shipments.CourierPartner",
        related_name="serviceability_rules",
        on_delete=models.CASCADE,
    )
    store = models.ForeignKey(
        "stores.Store",
        related_name="courier_serviceability_rules",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    country_code = models.CharField(max_length=2, blank=True)
    postal_code = models.CharField(max_length=32, blank=True)
    postal_code_prefix = models.CharField(max_length=16, blank=True)
    handling_time_days = models.PositiveIntegerField(default=0)
    transit_days = models.PositiveIntegerField(default=3)
    pickup_available = models.BooleanField(default=True)
    serviceable = models.BooleanField(default=True)
    cod_available = models.BooleanField(default=False)
    priority = models.PositiveIntegerField(default=100)

    class Meta:
        ordering = ("priority", "id")

    def __str__(self) -> str:
        return f"{self.courier_partner.name} / {self.postal_code or self.postal_code_prefix or self.country_code}"


class CourierRule(BaseModel):
    RULE_SERVICEABILITY = "serviceability"
    RULE_BOOKING = "booking"
    RULE_LABEL = "label"
    RULE_PICKUP = "pickup"
    RULE_TRACKING = "tracking"
    RULE_RETURN = "return"
    RULE_SETTLEMENT = "settlement"

    RULE_CHOICES = [
        (RULE_SERVICEABILITY, "Serviceability"),
        (RULE_BOOKING, "Booking"),
        (RULE_LABEL, "Label"),
        (RULE_PICKUP, "Pickup"),
        (RULE_TRACKING, "Tracking"),
        (RULE_RETURN, "Return"),
        (RULE_SETTLEMENT, "Settlement"),
    ]

    courier_partner = models.ForeignKey(
        "shipments.CourierPartner",
        related_name="rules",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=255)
    rule_type = models.CharField(max_length=32, choices=RULE_CHOICES)
    conditions = models.JSONField(default=dict, blank=True)
    actions = models.JSONField(default=dict, blank=True)
    priority = models.PositiveIntegerField(default=100)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ("priority", "name")

    def __str__(self) -> str:
        return self.name


class CourierShipmentEvent(BaseModel):
    shipment = models.ForeignKey(Shipment, related_name="events", on_delete=models.CASCADE)
    event_code = models.CharField(max_length=64)
    status = models.CharField(max_length=64)
    description = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("occurred_at", "created_at")

    def __str__(self) -> str:
        return f"{self.shipment.tracking_number} / {self.status}"


class CourierPickupSchedule(BaseModel):
    STATUS_REQUESTED = "requested"
    STATUS_CONFIRMED = "confirmed"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_REQUESTED, "Requested"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    shipment = models.ForeignKey(Shipment, related_name="pickup_schedules", on_delete=models.CASCADE)
    courier_partner = models.ForeignKey(
        "shipments.CourierPartner",
        related_name="pickup_schedules",
        on_delete=models.CASCADE,
    )
    pickup_date = models.DateField()
    pickup_slot = models.CharField(max_length=64, blank=True)
    pickup_reference = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_REQUESTED)
    payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("pickup_date",)

    def __str__(self) -> str:
        return f"{self.shipment.tracking_number} / {self.pickup_date}"


class CourierReturnPickup(BaseModel):
    STATUS_REQUESTED = "requested"
    STATUS_CONFIRMED = "confirmed"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_REQUESTED, "Requested"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    order = models.ForeignKey("orders.Order", related_name="return_courier_pickups", on_delete=models.CASCADE)
    shipment = models.ForeignKey(
        Shipment,
        related_name="return_courier_pickups",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    courier_partner = models.ForeignKey(
        "shipments.CourierPartner",
        related_name="return_pickups",
        on_delete=models.CASCADE,
    )
    pickup_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_REQUESTED)
    pickup_reference = models.CharField(max_length=120, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("pickup_date",)

    def __str__(self) -> str:
        return f"{self.order.number} / return pickup"


class CourierPerformanceReport(BaseModel):
    courier_partner = models.ForeignKey(
        "shipments.CourierPartner",
        related_name="performance_reports",
        on_delete=models.CASCADE,
    )
    period_start = models.DateField()
    period_end = models.DateField()
    total_shipments = models.PositiveIntegerField(default=0)
    delivered_shipments = models.PositiveIntegerField(default=0)
    cancelled_shipments = models.PositiveIntegerField(default=0)
    return_pickups = models.PositiveIntegerField(default=0)
    reverse_logistics_count = models.PositiveIntegerField(default=0)
    avg_delivery_hours = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    on_time_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    generated_at = models.DateTimeField(default=timezone.now)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-period_end", "-generated_at")

    def __str__(self) -> str:
        return f"{self.courier_partner.name} / {self.period_start} - {self.period_end}"


class FulfillmentRecord(BaseModel):
    MODE_BOOK_COURIER = "book_courier"
    MODE_SYNC_ONLY = "sync_only"
    MODE_OFFLINE = "offline"

    MODE_CHOICES = [
        (MODE_BOOK_COURIER, "Book courier"),
        (MODE_SYNC_ONLY, "Sync only"),
        (MODE_OFFLINE, "Offline"),
    ]

    STATUS_PENDING = "pending"
    STATUS_ACTIVE = "active"
    STATUS_COMPLETED = "completed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_COMPLETED, "Completed"),
    ]

    order = models.ForeignKey(
        "orders.Order",
        related_name="fulfillment_records",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    offline_sale = models.ForeignKey(
        "inventory.OfflineSale",
        related_name="fulfillment_records",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    connector = models.ForeignKey(
        "marketplace.MarketplaceConnector",
        related_name="fulfillment_records",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    source_channel = models.CharField(max_length=32)
    flow_type = models.CharField(max_length=32, choices=Shipment.FLOW_CHOICES)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    courier_booking_required = models.BooleanField(default=False)
    stock_sync_enabled = models.BooleanField(default=True)
    return_sync_enabled = models.BooleanField(default=True)
    refund_sync_enabled = models.BooleanField(default=True)
    settlement_sync_enabled = models.BooleanField(default=True)
    report_sync_enabled = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"{self.source_channel} / {self.flow_type}"


class CourierPartner(BaseModel):
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    service_regions = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=32, default="draft")
    config = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return self.name
