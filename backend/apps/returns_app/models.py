from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.common.models import BaseModel


class ReturnRequest(BaseModel):
    """
    Manages the customer return and refund process.
    """
    STATUS_REQUESTED = "requested"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_PICKUP_SCHEDULED = "pickup_scheduled"
    STATUS_PICKUP_COMPLETED = "pickup_completed"
    STATUS_QC_PENDING = "qc_pending"
    STATUS_QC_PASSED = "qc_passed"
    STATUS_QC_FAILED = "qc_failed"
    STATUS_REFUND_APPROVED = "refund_approved"
    STATUS_REFUND_COMPLETED = "refund_completed"
    STATUS_COMPLETED = "completed"

    # Compatibility aliases for inventory signals
    STATUS_QC_APPROVED = "qc_passed"
    STATUS_QC_REJECTED = "qc_failed"


    STATUS_CHOICES = [
        (STATUS_REQUESTED, "Return Requested"),
        (STATUS_APPROVED, "Request Approved"),
        (STATUS_REJECTED, "Request Rejected"),
        (STATUS_PICKUP_SCHEDULED, "Pickup Scheduled"),
        (STATUS_PICKUP_COMPLETED, "Pickup Completed"),
        (STATUS_QC_PENDING, "QC Pending"),
        (STATUS_QC_PASSED, "QC Passed"),
        (STATUS_QC_FAILED, "QC Failed"),
        (STATUS_REFUND_APPROVED, "Refund Approved"),
        (STATUS_REFUND_COMPLETED, "Refund Completed"),
        (STATUS_COMPLETED, "Return Completed"),
    ]

    return_number = models.CharField(max_length=50, unique=True, db_index=True)
    order = models.ForeignKey("orders.Order", related_name="return_requests", on_delete=models.PROTECT)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="return_requests", on_delete=models.PROTECT)
    retailer = models.ForeignKey("retailers.Retailer", related_name="return_requests", on_delete=models.PROTECT)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_REQUESTED)
    
    reason = models.TextField(help_text="Customer reason for return")
    rejection_reason = models.TextField(blank=True, null=True)
    
    # Pickup details
    pickup_address = models.TextField(blank=True, null=True)
    pickup_date = models.DateField(blank=True, null=True)
    pickup_carrier = models.CharField(max_length=100, blank=True, null=True)
    pickup_tracking_number = models.CharField(max_length=100, blank=True, null=True)
    
    # Financials
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    reviewed_at = models.DateTimeField(blank=True, null=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        related_name="reviewed_returns", 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL
    )

    def __str__(self) -> str:
        return f"{self.return_number} ({self.status})"


class ReturnItem(BaseModel):
    """
    Line items within a ReturnRequest.
    """
    DECISION_RESTOCKED = "restocked"
    DECISION_DISCARDED = "discarded"
    DECISION_OUTLET = "outlet"

    DECISION_CHOICES = [
        (DECISION_RESTOCKED, "Restocked in Warehouse"),
        (DECISION_DISCARDED, "Discarded (Damaged)"),
        (DECISION_OUTLET, "Sent to Outlet Store"),
    ]

    return_request = models.ForeignKey(ReturnRequest, related_name="items", on_delete=models.CASCADE)
    order_item = models.ForeignKey("orders.OrderItem", related_name="return_items", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    
    # Quality Control
    qc_status = models.CharField(
        max_length=32, 
        choices=[("pending", "Pending"), ("passed", "Passed"), ("failed", "Failed")], 
        default="pending"
    )
    qc_note = models.TextField(blank=True)
    
    # Inventory action
    restock_decision = models.CharField(max_length=32, choices=DECISION_CHOICES, blank=True, null=True)
    restocked_at = models.DateTimeField(blank=True, null=True)

    def __str__(self) -> str:
        return f"{self.order_item.product.name} x {self.quantity}"


class ReturnTimeline(BaseModel):
    """
    Visual timeline for return/refund status changes.
    Customer, Retailer, and Admin must see this.
    """
    return_request = models.ForeignKey(ReturnRequest, related_name="timeline_entries", on_delete=models.CASCADE)
    status = models.CharField(max_length=32)
    title = models.CharField(max_length=255)
    note = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        related_name="return_timeline_entries", 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL
    )
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("occurred_at", "created_at")

    def __str__(self) -> str:
        return f"{self.return_request.return_number} - {self.status}"
