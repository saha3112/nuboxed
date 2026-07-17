from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.payments.views import (
    PaymentGatewayViewSet,
    PaymentTransactionViewSet,
    RefundTransactionViewSet,
    InvoiceViewSet,
    WalletViewSet,
    RetailerSettlementViewSet,
    PlatformCommissionViewSet,
    GatewayChargesViewSet,
    FinancialAuditLogViewSet,
)

router = DefaultRouter()
router.register(r"gateways", PaymentGatewayViewSet, basename="gateway")
router.register(r"transactions", PaymentTransactionViewSet, basename="transaction")
router.register(r"refunds", RefundTransactionViewSet, basename="refund")
router.register(r"invoices", InvoiceViewSet, basename="invoice")
router.register(r"wallets", WalletViewSet, basename="wallet")
router.register(r"settlements", RetailerSettlementViewSet, basename="settlement")
router.register(r"commissions", PlatformCommissionViewSet, basename="commission")
router.register(r"gateway-charges", GatewayChargesViewSet, basename="gateway-charge")
router.register(r"audit-logs", FinancialAuditLogViewSet, basename="audit-log")

urlpatterns = [
    path("", include(router.urls)),
]
