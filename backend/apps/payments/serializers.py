from rest_framework import serializers
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
)


class PaymentGatewaySerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentGateway
        fields = ["id", "code", "name", "provider", "status", "is_live", "config", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class GatewayChargesSerializer(serializers.ModelSerializer):
    class Meta:
        model = GatewayCharges
        fields = ["id", "payment_transaction", "gateway_code", "charge_amount", "currency", "gateway_fee_details"]


class PaymentTransactionSerializer(serializers.ModelSerializer):
    gateway_charge = GatewayChargesSerializer(read_only=True)
    gateway_name = serializers.CharField(source="gateway.name", read_only=True)

    class Meta:
        model = PaymentTransaction
        fields = [
            "id", "transaction_number", "order", "gateway", "gateway_name", "amount", "currency",
            "status", "gateway_transaction_id", "gateway_response", "error_code",
            "error_message", "captured_at", "gateway_charge", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "transaction_number", "gateway_charge", "captured_at", "created_at", "updated_at"]


class RefundTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RefundTransaction
        fields = [
            "id", "refund_number", "payment_transaction", "amount", "currency",
            "status", "gateway_refund_id", "reason", "gateway_response", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "refund_number", "gateway_response", "created_at", "updated_at"]


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ["id", "product_name", "product_sku", "quantity", "unit_price", "discount_amount", "tax_rate", "tax_amount", "line_total"]


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    customer_email = serializers.EmailField(source="customer.email", read_only=True)
    retailer_name = serializers.CharField(source="retailer.legal_name", read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "invoice_number", "order", "customer", "customer_email", "retailer", "retailer_name",
            "status", "issue_date", "due_date", "currency", "subtotal_amount", "discount_amount",
            "tax_amount", "total_amount", "tax_type", "billing_name", "billing_address",
            "customer_tax_id", "retailer_tax_id", "pdf_file", "items", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "invoice_number", "pdf_file", "created_at", "updated_at"]


class CreditNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditNote
        fields = ["id", "credit_note_number", "invoice", "amount", "currency", "status", "reason", "issued_at", "issued_by"]
        read_only_fields = ["id", "credit_note_number", "issued_at", "issued_by"]


class DebitNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = DebitNote
        fields = ["id", "debit_note_number", "invoice", "amount", "currency", "status", "reason", "issued_at", "issued_by"]
        read_only_fields = ["id", "debit_note_number", "issued_at", "issued_by"]


class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = ["id", "wallet", "amount", "currency", "transaction_type", "status", "reference", "description", "created_at"]
        read_only_fields = ["id", "created_at"]


class WalletSerializer(serializers.ModelSerializer):
    transactions = WalletTransactionSerializer(many=True, read_only=True)
    owner_name = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = ["id", "retailer", "user", "owner_name", "balance", "currency", "status", "transactions", "created_at", "updated_at"]
        read_only_fields = ["id", "balance", "created_at", "updated_at"]

    def get_owner_name(self, obj) -> str:
        if obj.retailer:
            return obj.retailer.legal_name
        if obj.user:
            return obj.user.email
        return "System"


class RetailerSettlementSerializer(serializers.ModelSerializer):
    retailer_name = serializers.CharField(source="retailer.legal_name", read_only=True)

    class Meta:
        model = RetailerSettlement
        fields = [
            "id", "settlement_number", "retailer", "retailer_name", "gross_amount",
            "commission_amount", "gateway_charges_amount", "net_amount", "currency",
            "status", "bank_details", "payout_reference", "paid_at", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "settlement_number", "net_amount", "paid_at", "created_at", "updated_at"]


class PlatformCommissionSerializer(serializers.ModelSerializer):
    retailer_name = serializers.CharField(source="retailer.legal_name", read_only=True)
    order_number = serializers.CharField(source="order.number", read_only=True)

    class Meta:
        model = PlatformCommission
        fields = [
            "id", "order", "order_number", "invoice", "retailer", "retailer_name",
            "gross_amount", "commission_rate", "commission_amount", "currency", "status", "created_at"
        ]
        read_only_fields = ["id", "created_at"]


class FinancialAuditLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True)

    class Meta:
        model = FinancialAuditLog
        fields = [
            "id", "actor", "actor_email", "event_type", "target_type", "target_id",
            "amount", "currency", "previous_state", "new_state", "description", "created_at"
        ]
        read_only_fields = ["id", "created_at"]
