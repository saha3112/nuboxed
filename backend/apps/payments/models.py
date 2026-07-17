from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.common.models import BaseModel


class PaymentGateway(BaseModel):
    """
    Super Admin controlled payment gateways.
    Supports Stripe, PayPal, Razorpay, Bank transfer, COD, and Future gateways.
    """
    STATUS_DRAFT = "draft"
    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_INACTIVE, "Inactive"),
    ]

    code = models.CharField(max_length=64, unique=True, help_text="e.g. stripe, paypal, razorpay, bank_transfer, cod")
    name = models.CharField(max_length=255)
    provider = models.CharField(max_length=120, help_text="Adapter or integration provider class name")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    is_live = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True, help_text="API keys, webhook secrets, etc.")

    def __str__(self) -> str:
        return f"{self.name} ({self.code.upper()})"


class PaymentTransaction(BaseModel):
    """
    Tracks payment attempts and status for an order.
    """
    STATUS_PENDING = "pending"
    STATUS_AUTHORIZED = "authorized"
    STATUS_CAPTURED = "captured"
    STATUS_FAILED = "failed"
    STATUS_REFUNDED = "refunded"
    STATUS_VOIDED = "voided"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_AUTHORIZED, "Authorized"),
        (STATUS_CAPTURED, "Captured"),
        (STATUS_FAILED, "Failed"),
        (STATUS_REFUNDED, "Refunded"),
        (STATUS_VOIDED, "Voided"),
    ]

    transaction_number = models.CharField(max_length=100, unique=True, db_index=True)
    order = models.ForeignKey("orders.Order", related_name="payment_transactions", on_delete=models.CASCADE)
    gateway = models.ForeignKey(PaymentGateway, related_name="transactions", on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR", help_text="3-letter ISO currency code")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING)
    gateway_transaction_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    gateway_response = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=100, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    captured_at = models.DateTimeField(blank=True, null=True)

    def __str__(self) -> str:
        return f"{self.transaction_number} - {self.status}"


class RefundTransaction(BaseModel):
    """
    Tracks refund attempts against a captured PaymentTransaction.
    """
    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    refund_number = models.CharField(max_length=100, unique=True, db_index=True)
    payment_transaction = models.ForeignKey(PaymentTransaction, related_name="refunds", on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING)
    gateway_refund_id = models.CharField(max_length=255, blank=True, null=True)
    reason = models.TextField(blank=True)
    gateway_response = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return f"Refund {self.refund_number} - {self.status}"


class Invoice(BaseModel):
    """
    Invoice generated for an Order.
    Multi-currency and VAT/GST ready.
    """
    STATUS_DRAFT = "draft"
    STATUS_SENT = "sent"
    STATUS_PAID = "paid"
    STATUS_PARTIALLY_PAID = "partially_paid"
    STATUS_VOIDED = "voided"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SENT, "Sent"),
        (STATUS_PAID, "Paid"),
        (STATUS_PARTIALLY_PAID, "Partially Paid"),
        (STATUS_VOIDED, "Voided"),
    ]

    TAX_TYPE_VAT = "vat"
    TAX_TYPE_GST = "gst"
    TAX_TYPE_NONE = "none"

    TAX_TYPE_CHOICES = [
        (TAX_TYPE_VAT, "Value Added Tax (VAT)"),
        (TAX_TYPE_GST, "Goods and Services Tax (GST)"),
        (TAX_TYPE_NONE, "None/Exempt"),
    ]

    invoice_number = models.CharField(max_length=100, unique=True, db_index=True)
    order = models.ForeignKey("orders.Order", related_name="invoices", on_delete=models.PROTECT)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="invoices", on_delete=models.PROTECT)
    retailer = models.ForeignKey("retailers.Retailer", related_name="invoices", on_delete=models.PROTECT)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    
    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    
    # Financial fields (Multi-currency ready)
    currency = models.CharField(max_length=3, default="EUR")
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Tax structures
    tax_type = models.CharField(max_length=16, choices=TAX_TYPE_CHOICES, default=TAX_TYPE_VAT)
    billing_name = models.CharField(max_length=255)
    billing_address = models.TextField()
    customer_tax_id = models.CharField(max_length=64, blank=True, null=True, help_text="VAT/GST number of the customer")
    retailer_tax_id = models.CharField(max_length=64, blank=True, null=True, help_text="VAT/GST number of the retailer")
    
    pdf_file = models.FileField(upload_to="invoices/", blank=True, null=True)

    def __str__(self) -> str:
        return self.invoice_number


class InvoiceItem(BaseModel):
    """
    Line items for an Invoice.
    """
    invoice = models.ForeignKey(Invoice, related_name="items", on_delete=models.CASCADE)
    product_name = models.CharField(max_length=255)
    product_sku = models.CharField(max_length=100, blank=True, null=True)
    quantity = models.PositiveIntegerField(default=1)
    
    # Unit prices
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Tax details
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="Percentage rate, e.g. 19.00 for 19%")
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self) -> str:
        return f"{self.product_name} x {self.quantity}"


class CreditNote(BaseModel):
    """
    Credit notes are issued to reduce the amount the customer owes or record refunds on an invoice.
    """
    STATUS_ISSUED = "issued"
    STATUS_VOIDED = "voided"

    STATUS_CHOICES = [
        (STATUS_ISSUED, "Issued"),
        (STATUS_VOIDED, "Voided"),
    ]

    credit_note_number = models.CharField(max_length=100, unique=True, db_index=True)
    invoice = models.ForeignKey(Invoice, related_name="credit_notes", on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_ISSUED)
    reason = models.TextField()
    issued_at = models.DateTimeField(default=timezone.now)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self) -> str:
        return self.credit_note_number


class DebitNote(BaseModel):
    """
    Debit notes are issued to increase the invoice amount due (e.g. for extra charges).
    """
    STATUS_ISSUED = "issued"
    STATUS_VOIDED = "voided"

    STATUS_CHOICES = [
        (STATUS_ISSUED, "Issued"),
        (STATUS_VOIDED, "Voided"),
    ]

    debit_note_number = models.CharField(max_length=100, unique=True, db_index=True)
    invoice = models.ForeignKey(Invoice, related_name="debit_notes", on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_ISSUED)
    reason = models.TextField()
    issued_at = models.DateTimeField(default=timezone.now)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self) -> str:
        return self.debit_note_number


class Wallet(BaseModel):
    """
    Wallet structure for storing virtual balances.
    Can belong to either a Retailer or a Customer User.
    Multi-currency ready.
    """
    STATUS_ACTIVE = "active"
    STATUS_FROZEN = "frozen"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_FROZEN, "Frozen"),
    ]

    retailer = models.OneToOneField("retailers.Retailer", related_name="wallet", on_delete=models.PROTECT, null=True, blank=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="wallet", on_delete=models.PROTECT, null=True, blank=True)
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0.00)
    currency = models.CharField(max_length=3, default="EUR")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_ACTIVE)

    def __str__(self) -> str:
        owner = self.retailer.legal_name if self.retailer else (self.user.email if self.user else "System")
        return f"Wallet - {owner} ({self.balance} {self.currency})"


class WalletTransaction(BaseModel):
    """
    Ledger recording balance modifications to a Wallet.
    """
    TYPE_DEPOSIT = "deposit"
    TYPE_WITHDRAWAL = "withdrawal"
    TYPE_COMMISSION = "commission"
    TYPE_SETTLEMENT = "settlement"
    TYPE_REFUND = "refund"
    TYPE_ADJUSTMENT = "adjustment"

    TYPE_CHOICES = [
        (TYPE_DEPOSIT, "Deposit"),
        (TYPE_WITHDRAWAL, "Withdrawal"),
        (TYPE_COMMISSION, "Commission"),
        (TYPE_SETTLEMENT, "Settlement Payout"),
        (TYPE_REFUND, "Refund"),
        (TYPE_ADJUSTMENT, "Adjustment"),
    ]

    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    wallet = models.ForeignKey(Wallet, related_name="transactions", on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Positive for deposits, negative for withdrawals")
    currency = models.CharField(max_length=3, default="EUR")
    transaction_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_COMPLETED)
    reference = models.CharField(max_length=120, blank=True, null=True, help_text="e.g. order_id, settlement_id, refund_id")
    description = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"{self.transaction_type.upper()} ({self.amount} {self.currency}) - {self.status}"


class RetailerSettlement(BaseModel):
    """
    Processes payouts to the Retailer.
    """
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

    settlement_number = models.CharField(max_length=100, unique=True, db_index=True)
    retailer = models.ForeignKey("retailers.Retailer", related_name="settlements", on_delete=models.PROTECT)
    
    # Financial breakdown
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Platform commission deducted")
    gateway_charges_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Gateway fee deducted")
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Retailer payout amount: gross - commission - gateway_charges")
    currency = models.CharField(max_length=3, default="EUR")
    
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING)
    bank_details = models.JSONField(default=dict, blank=True, help_text="Bank details used for settlement payout")
    payout_reference = models.CharField(max_length=255, blank=True, null=True, help_text="Bank transfer ID, transaction ID, etc.")
    
    paid_at = models.DateTimeField(blank=True, null=True)

    def __str__(self) -> str:
        return f"{self.settlement_number} - {self.retailer.legal_name} ({self.net_amount} {self.currency})"


class PlatformCommission(BaseModel):
    """
    Tracks platform commissions earned from sales.
    """
    STATUS_PENDING = "pending"
    STATUS_EARNED = "earned"
    STATUS_REFUNDED = "refunded"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_EARNED, "Earned"),
        (STATUS_REFUNDED, "Refunded"),
    ]

    order = models.ForeignKey("orders.Order", related_name="commissions", on_delete=models.PROTECT)
    invoice = models.ForeignKey(Invoice, related_name="commissions", on_delete=models.PROTECT, null=True, blank=True)
    retailer = models.ForeignKey("retailers.Retailer", related_name="commissions", on_delete=models.PROTECT)
    
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, help_text="Percentage rate, e.g. 10.00 for 10%")
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING)

    def __str__(self) -> str:
        return f"Comm: {self.commission_amount} {self.currency} on Order {self.order.number}"


class GatewayCharges(BaseModel):
    """
    Tracks payment gateway processing fees.
    """
    payment_transaction = models.OneToOneField(PaymentTransaction, related_name="gateway_charge", on_delete=models.CASCADE)
    gateway_code = models.CharField(max_length=64)
    charge_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    gateway_fee_details = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return f"Fee: {self.charge_amount} {self.currency} ({self.gateway_code})"


class FinancialAuditLog(BaseModel):
    """
    High-integrity, immutable audit log for financial events.
    """
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    event_type = models.CharField(max_length=120, help_text="e.g. WALLET_DEPOSIT, INVOICE_GENERATED, SETTLEMENT_PAID")
    target_type = models.CharField(max_length=120, help_text="Model class name, e.g. Wallet, Invoice")
    target_id = models.CharField(max_length=64, help_text="UUID of target model instance")
    
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True, null=True)
    
    previous_state = models.JSONField(default=dict, blank=True)
    new_state = models.JSONField(default=dict, blank=True)
    description = models.TextField()

    def __str__(self) -> str:
        return f"{self.event_type} - {self.target_type} ({self.target_id})"


class Payment(BaseModel):
    """
    Deprecated: Preserved for backward compatibility with orders app.
    Use PaymentTransaction for detailed financial tracking.
    """
    order = models.ForeignKey("orders.Order", related_name="payments", on_delete=models.CASCADE)
    provider = models.CharField(max_length=64)
    external_reference = models.CharField(max_length=120, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=32, default="pending")

    def __str__(self) -> str:
        return self.external_reference

