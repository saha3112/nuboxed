from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q

from apps.rbac.permissions import CommerceAccessPermission
from apps.retailers.models import Retailer
from apps.orders.models import Order
from apps.payments.models import (
    PaymentGateway,
    PaymentTransaction,
    RefundTransaction,
    Invoice,
    CreditNote,
    DebitNote,
    Wallet,
    WalletTransaction,
    RetailerSettlement,
    PlatformCommission,
    GatewayCharges,
    FinancialAuditLog,
)
from apps.payments.serializers import (
    PaymentGatewaySerializer,
    PaymentTransactionSerializer,
    RefundTransactionSerializer,
    InvoiceSerializer,
    CreditNoteSerializer,
    DebitNoteSerializer,
    WalletSerializer,
    WalletTransactionSerializer,
    RetailerSettlementSerializer,
    PlatformCommissionSerializer,
    GatewayChargesSerializer,
    FinancialAuditLogSerializer,
)
from apps.payments.services import (
    record_payment_transaction,
    process_refund,
    create_credit_note,
    create_debit_note,
    process_retailer_settlement,
    complete_retailer_settlement,
    get_or_create_wallet,
)


def get_user_retailer_ids(user):
    """
    Helper to get all retailer IDs accessible by the user.
    """
    if user.is_super_admin:
        return None
    # Member of Account which has a RetailerProfile
    accounts = user.account_memberships.filter(status="active").values_list("account_id", flat=True)
    return list(Retailer.objects.filter(account_id__in=accounts).values_list("id", flat=True))


class PaymentGatewayViewSet(viewsets.ModelViewSet):
    """
    Super Admin controls gateways. Retailers/Customers can view active ones.
    """
    queryset = PaymentGateway.objects.all()
    serializer_class = PaymentGatewaySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_super_admin:
            return PaymentGateway.objects.all()
        # Non-admins can only see active/live gateways
        return PaymentGateway.objects.filter(status=PaymentGateway.STATUS_ACTIVE)

    def check_permissions(self, request):
        super().check_permissions(request)
        # Write actions require super admin
        if self.action in ["create", "update", "partial_update", "destroy"]:
            if not request.user.is_super_admin:
                self.permission_denied(request, message="Only Super Admins can manage payment gateways.")


class PaymentTransactionViewSet(viewsets.ModelViewSet):
    queryset = PaymentTransaction.objects.all()
    serializer_class = PaymentTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return PaymentTransaction.objects.all()

        retailer_ids = get_user_retailer_ids(user)
        # Customers see their own orders, Retailers see orders sold by them
        return PaymentTransaction.objects.filter(
            Q(order__customer=user) | Q(order__retailer_id__in=retailer_ids)
        ).distinct()

    def create(self, request, *args, **kwargs):
        """
        Creates a new payment attempt (mock gateway call).
        """
        order_id = request.data.get("order")
        gateway_id = request.data.get("gateway")
        amount = request.data.get("amount")
        currency = request.data.get("currency", "EUR")
        status_input = request.data.get("status", PaymentTransaction.STATUS_CAPTURED) # default capture

        order = get_object_or_404(Order, id=order_id)
        gateway = get_object_or_404(PaymentGateway, id=gateway_id)

        # Check permissions: customer of order, or retailer of order
        if not request.user.is_super_admin:
            retailer_ids = get_user_retailer_ids(request.user)
            if order.customer != request.user and order.retailer_id not in retailer_ids:
                return Response({"detail": "Not authorized to pay for this order."}, status=status.HTTP_403_FORBIDDEN)

        # Mock API gateway details
        gateway_transaction_id = f"ch_{uuid_mock()}" if status_input == PaymentTransaction.STATUS_CAPTURED else None
        gateway_response = {
            "mocked": True,
            "provider": gateway.code,
            "card_brand": "Visa",
            "last4": "4242"
        }

        tx = record_payment_transaction(
            order=order,
            gateway=gateway,
            amount=amount,
            currency=currency,
            status=status_input,
            gateway_transaction_id=gateway_transaction_id,
            gateway_response=gateway_response,
            actor=request.user
        )

        serializer = self.get_serializer(tx)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class RefundTransactionViewSet(viewsets.ModelViewSet):
    queryset = RefundTransaction.objects.all()
    serializer_class = RefundTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return RefundTransaction.objects.all()

        retailer_ids = get_user_retailer_ids(user)
        return RefundTransaction.objects.filter(
            Q(payment_transaction__order__customer=user) | 
            Q(payment_transaction__order__retailer_id__in=retailer_ids)
        ).distinct()

    def create(self, request, *args, **kwargs):
        """
        Creates a refund against a payment transaction.
        """
        tx_id = request.data.get("payment_transaction")
        amount = request.data.get("amount")
        reason = request.data.get("reason", "")

        tx = get_object_or_404(PaymentTransaction, id=tx_id)

        # Non-admins: only retailer who sold the order can refund
        if not request.user.is_super_admin:
            retailer_ids = get_user_retailer_ids(request.user)
            if tx.order.retailer_id not in retailer_ids:
                return Response({"detail": "Only the retailer associated with this order can refund it."}, status=status.HTTP_403_FORBIDDEN)

        try:
            refund = process_refund(
                payment_transaction=tx,
                amount=amount,
                reason=reason,
                actor=request.user
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(refund)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return Invoice.objects.all()

        retailer_ids = get_user_retailer_ids(user)
        return Invoice.objects.filter(
            Q(customer=user) | Q(retailer_id__in=retailer_ids)
        ).distinct()

    @action(detail=True, methods=["post"], url_path="credit-note")
    def add_credit_note(self, request, pk=None):
        invoice = self.get_object()
        amount = request.data.get("amount")
        reason = request.data.get("reason", "")

        # Retailer check
        if not request.user.is_super_admin:
            retailer_ids = get_user_retailer_ids(request.user)
            if invoice.retailer_id not in retailer_ids:
                return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        try:
            cn = create_credit_note(invoice, amount, reason, actor=request.user)
            serializer = CreditNoteSerializer(cn)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="debit-note")
    def add_debit_note(self, request, pk=None):
        invoice = self.get_object()
        amount = request.data.get("amount")
        reason = request.data.get("reason", "")

        # Retailer check
        if not request.user.is_super_admin:
            retailer_ids = get_user_retailer_ids(request.user)
            if invoice.retailer_id not in retailer_ids:
                return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        try:
            dn = create_debit_note(invoice, amount, reason, actor=request.user)
            serializer = DebitNoteSerializer(dn)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class WalletViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Allows viewing current wallet balance and history.
    """
    queryset = Wallet.objects.all()
    serializer_class = WalletSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return Wallet.objects.all()

        retailer_ids = get_user_retailer_ids(user)
        return Wallet.objects.filter(
            Q(user=user) | Q(retailer_id__in=retailer_ids)
        ).distinct()

    @action(detail=False, methods=["get"], url_path="my-wallet")
    def my_wallet(self, request):
        user = request.user
        # Prioritize Retailer wallet if user is staff/retailer, otherwise Customer wallet
        retailer_ids = get_user_retailer_ids(user)
        if retailer_ids:
            # Return first retailer's wallet
            retailer = Retailer.objects.get(id=retailer_ids[0])
            wallet = get_or_create_wallet(retailer, "retailer", "EUR")
        else:
            wallet = get_or_create_wallet(user, "customer", "EUR")

        serializer = self.get_serializer(wallet)
        return Response(serializer.data)


class RetailerSettlementViewSet(viewsets.ModelViewSet):
    queryset = RetailerSettlement.objects.all()
    serializer_class = RetailerSettlementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return RetailerSettlement.objects.all()

        retailer_ids = get_user_retailer_ids(user)
        return RetailerSettlement.objects.filter(retailer_id__in=retailer_ids)

    def create(self, request, *args, **kwargs):
        """
        Request a payout/settlement from the wallet.
        """
        retailer_id = request.data.get("retailer")
        amount = request.data.get("amount")
        currency = request.data.get("currency", "EUR")
        bank_details = request.data.get("bank_details", {})

        retailer = get_object_or_404(Retailer, id=retailer_id)

        # Permission check: must be member of this retailer
        if not request.user.is_super_admin:
            retailer_ids = get_user_retailer_ids(request.user)
            if retailer.id not in retailer_ids:
                return Response({"detail": "Not authorized to request settlements for this retailer."}, status=status.HTTP_403_FORBIDDEN)

        try:
            settlement = process_retailer_settlement(
                retailer=retailer,
                amount=amount,
                currency=currency,
                bank_details=bank_details,
                actor=request.user
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(settlement)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        """
        Super Admin completes/releases the settlement payout.
        """
        if not request.user.is_super_admin:
            return Response({"detail": "Only Super Admins can complete settlements."}, status=status.HTTP_403_FORBIDDEN)

        settlement = self.get_object()
        payout_ref = request.data.get("payout_reference")

        if not payout_ref:
            return Response({"detail": "payout_reference is required to complete settlement."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            settlement = complete_retailer_settlement(settlement, payout_ref, actor=request.user)
            serializer = self.get_serializer(settlement)
            return Response(serializer.data)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PlatformCommissionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PlatformCommission.objects.all()
    serializer_class = PlatformCommissionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return PlatformCommission.objects.all()

        retailer_ids = get_user_retailer_ids(user)
        return PlatformCommission.objects.filter(retailer_id__in=retailer_ids)


class GatewayChargesViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = GatewayCharges.objects.all()
    serializer_class = GatewayChargesSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return GatewayCharges.objects.all()

        retailer_ids = get_user_retailer_ids(user)
        return GatewayCharges.objects.filter(payment_transaction__order__retailer_id__in=retailer_ids)


class FinancialAuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Strictly for Super Admins / Auditors.
    """
    queryset = FinancialAuditLog.objects.all()
    serializer_class = FinancialAuditLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def check_permissions(self, request):
        super().check_permissions(request)
        if not request.user.is_super_admin:
            self.permission_denied(request, message="Only Super Admins can access financial audit logs.")

    def get_queryset(self):
        if not self.request.user.is_super_admin:
            return FinancialAuditLog.objects.none()
        return FinancialAuditLog.objects.all()


def uuid_mock():
    import uuid
    return uuid.uuid4().hex[:12]
