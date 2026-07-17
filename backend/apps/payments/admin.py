from django.contrib import admin
from apps.payments.models import (
    PaymentGateway,
    PaymentTransaction,
    RefundTransaction,
    Invoice,
    InvoiceItem,
    CreditNote,
    DebitNote,
    Wallet,
    WalletTransaction,
    RetailerSettlement,
    PlatformCommission,
    GatewayCharges,
    FinancialAuditLog,
    Payment,
)


@admin.register(PaymentGateway)
class PaymentGatewayAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "status", "is_live", "created_at")
    list_filter = ("status", "is_live")
    search_fields = ("code", "name")


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ("transaction_number", "order", "gateway", "amount", "currency", "status", "captured_at")
    list_filter = ("status", "currency", "gateway")
    search_fields = ("transaction_number", "gateway_transaction_id", "order__number")
    readonly_fields = ("transaction_number", "captured_at")


@admin.register(RefundTransaction)
class RefundTransactionAdmin(admin.ModelAdmin):
    list_display = ("refund_number", "payment_transaction", "amount", "currency", "status", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("refund_number", "gateway_refund_id", "payment_transaction__transaction_number")
    readonly_fields = ("refund_number",)


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "order", "customer", "retailer", "status", "total_amount", "currency", "issue_date")
    list_filter = ("status", "currency", "tax_type", "issue_date")
    search_fields = ("invoice_number", "order__number", "customer__email", "retailer__legal_name")
    inlines = [InvoiceItemInline]
    readonly_fields = ("invoice_number",)


@admin.register(CreditNote)
class CreditNoteAdmin(admin.ModelAdmin):
    list_display = ("credit_note_number", "invoice", "amount", "currency", "status", "issued_at")
    list_filter = ("status", "currency", "issued_at")
    search_fields = ("credit_note_number", "invoice__invoice_number")
    readonly_fields = ("credit_note_number",)


@admin.register(DebitNote)
class DebitNoteAdmin(admin.ModelAdmin):
    list_display = ("debit_note_number", "invoice", "amount", "currency", "status", "issued_at")
    list_filter = ("status", "currency", "issued_at")
    search_fields = ("debit_note_number", "invoice__invoice_number")
    readonly_fields = ("debit_note_number",)


class WalletTransactionInline(admin.TabularInline):
    model = WalletTransaction
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("id", "get_owner", "balance", "currency", "status", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("retailer__legal_name", "user__email")
    inlines = [WalletTransactionInline]

    def get_owner(self, obj):
        if obj.retailer:
            return f"Retailer: {obj.retailer.legal_name}"
        if obj.user:
            return f"Customer: {obj.user.email}"
        return "System"
    get_owner.short_description = "Owner"


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("wallet", "amount", "currency", "transaction_type", "status", "reference", "created_at")
    list_filter = ("transaction_type", "status", "currency")
    search_fields = ("wallet__retailer__legal_name", "wallet__user__email", "reference")


@admin.register(RetailerSettlement)
class RetailerSettlementAdmin(admin.ModelAdmin):
    list_display = ("settlement_number", "retailer", "gross_amount", "net_amount", "currency", "status", "paid_at")
    list_filter = ("status", "currency", "paid_at")
    search_fields = ("settlement_number", "retailer__legal_name", "payout_reference")
    readonly_fields = ("settlement_number",)


@admin.register(PlatformCommission)
class PlatformCommissionAdmin(admin.ModelAdmin):
    list_display = ("order", "retailer", "gross_amount", "commission_rate", "commission_amount", "currency", "status")
    list_filter = ("status", "currency")
    search_fields = ("order__number", "retailer__legal_name")


@admin.register(GatewayCharges)
class GatewayChargesAdmin(admin.ModelAdmin):
    list_display = ("payment_transaction", "gateway_code", "charge_amount", "currency")
    list_filter = ("gateway_code", "currency")
    search_fields = ("payment_transaction__transaction_number",)


@admin.register(FinancialAuditLog)
class FinancialAuditLogAdmin(admin.ModelAdmin):
    list_display = ("event_type", "target_type", "target_id", "amount", "currency", "actor", "created_at")
    list_filter = ("event_type", "target_type", "currency")
    search_fields = ("target_id", "actor__email", "description")
    readonly_fields = ("actor", "event_type", "target_type", "target_id", "amount", "currency", "previous_state", "new_state", "description")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("external_reference", "order", "provider", "amount", "status", "created_at")
    list_filter = ("status", "provider")
    search_fields = ("external_reference", "order__number")

