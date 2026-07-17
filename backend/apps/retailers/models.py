from django.db import models

from apps.common.models import BaseModel


class Retailer(BaseModel):
    STATUS_DRAFT = "draft"
    STATUS_PENDING = "pending_approval"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PENDING, "Pending approval"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    account = models.OneToOneField(
        "accounts.Account",
        related_name="retailer_profile",
        on_delete=models.CASCADE,
    )
    legal_name = models.CharField(max_length=255)
    vat_number = models.CharField(max_length=64, blank=True)
    display_name = models.CharField(max_length=255, blank=True)
    registration_number = models.CharField(max_length=120, blank=True)
    support_email = models.EmailField(blank=True)
    support_phone = models.CharField(max_length=32, blank=True)
    business_address = models.TextField(blank=True)
    business_type = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. Sole Proprietorship, Partnership, LLC")
    business_document = models.FileField(upload_to="retailer/documents/", blank=True, null=True, help_text="Business Registration Certificate")
    gst_certificate = models.FileField(upload_to="retailer/documents/", blank=True, null=True, help_text="GST / Tax Registration Certificate")
    pan_card = models.FileField(upload_to="retailer/documents/", blank=True, null=True, help_text="PAN Card / Tax ID Document")
    cancelled_cheque = models.FileField(upload_to="retailer/documents/", blank=True, null=True, help_text="Cancelled Cheque / Bank Statement")
    address_proof = models.FileField(upload_to="retailer/documents/", blank=True, null=True, help_text="Address Proof (Utility Bill, Aadhaar, etc.)")
    signature = models.FileField(upload_to="retailer/documents/", blank=True, null=True, help_text="Authorized Signatory Signature")
    msme_certificate = models.FileField(upload_to="retailer/documents/", blank=True, null=True, help_text="MSME / Udyam Registration (if applicable)")
    fssai_license = models.FileField(upload_to="retailer/documents/", blank=True, null=True, help_text="FSSAI License (if food products)")
    description = models.TextField(blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        "users.User",
        related_name="approved_retailers",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    approval_notes = models.TextField(blank=True)
    can_approve_reviews = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.legal_name
