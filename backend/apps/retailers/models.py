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
    custom_registration_data = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return self.legal_name


class SellerVerificationPageSetting(BaseModel):
    """Admin-editable copy and visibility for the seller document section."""

    singleton_key = models.CharField(max_length=32, unique=True, default="registration")
    section_title = models.CharField(max_length=160, default="Seller Verification Documents")
    section_description = models.TextField(
        blank=True,
        default="Upload documents to speed up your seller verification. All documents are optional during registration — you can upload them later from your profile.",
    )
    is_visible = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Seller verification page setting"
        verbose_name_plural = "Seller verification page settings"


class SellerVerificationDocumentSetting(BaseModel):
    """Controls each upload field rendered on retailer onboarding screens."""

    field_name = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=160)
    description = models.CharField(max_length=320, blank=True)
    icon_class = models.CharField(max_length=100, default="ph ph-file")
    sort_order = models.PositiveIntegerField(default=0)
    is_visible = models.BooleanField(default=True)
    is_required = models.BooleanField(default=False)

    class Meta:
        ordering = ("sort_order", "title")
        verbose_name = "Seller verification document"
        verbose_name_plural = "Seller verification documents"

    def __str__(self) -> str:
        return self.title


class SellerVerificationDocumentUpload(BaseModel):
    retailer = models.ForeignKey(Retailer, related_name="additional_verification_documents", on_delete=models.CASCADE)
    setting = models.ForeignKey(SellerVerificationDocumentSetting, related_name="uploads", on_delete=models.CASCADE)
    file = models.FileField(upload_to="retailer/documents/")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("retailer", "setting"), name="unique_retailer_verification_upload")]

    def __str__(self) -> str:
        return f"{self.retailer} — {self.setting.title}"


class RetailerRegistrationFieldSetting(BaseModel):
    FIELD_TEXT = "text"
    FIELD_TEXTAREA = "textarea"
    FIELD_SELECT = "select"
    FIELD_CHOICES = ((FIELD_TEXT, "Text"), (FIELD_TEXTAREA, "Textarea"), (FIELD_SELECT, "Select"))
    field_name = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=160)
    placeholder = models.CharField(max_length=255, blank=True)
    field_type = models.CharField(max_length=16, choices=FIELD_CHOICES, default=FIELD_TEXT)
    choices_text = models.TextField(blank=True, help_text="One option per line for Select fields")
    sort_order = models.PositiveIntegerField(default=0)
    is_visible = models.BooleanField(default=True)
    is_required = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)

    class Meta:
        ordering = ("sort_order", "title")

    def __str__(self) -> str:
        return self.title

    @property
    def choices_list(self):
        raw = self.choices_text or ""
        values = raw.splitlines() if "\n" in raw else raw.split(",")
        return [(line.strip(), line.strip()) for line in values if line.strip()]
