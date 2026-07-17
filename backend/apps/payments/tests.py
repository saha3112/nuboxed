from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status

from apps.accounts.models import Account
from apps.retailers.models import Retailer
from apps.orders.models import Order, OrderItem
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
from apps.payments.services import (
    get_or_create_wallet,
    modify_wallet_balance,
    generate_invoice_for_order,
    record_payment_transaction,
    process_refund,
    create_credit_note,
    create_debit_note,
    process_retailer_settlement,
    complete_retailer_settlement,
)

User = get_user_model()


class PaymentModuleTestCase(APITestCase):
    def setUp(self):
        # Create users
        self.super_admin = User.objects.create_superuser(
            email="admin@nuboxed.com",
            username="admin",
            password="password123",
            is_active=True
        )
        self.customer = User.objects.create_user(
            email="customer@gmail.com",
            username="customer",
            password="password123",
            is_active=True
        )
        self.retailer_user = User.objects.create_user(
            email="merchant@retailer.com",
            username="merchant",
            password="password123",
            is_active=True
        )

        # Create Account and Retailer
        self.account = Account.objects.create(
            name="Retailer Account",
            slug="retailer-account",
            owner=self.retailer_user,
            country_code="DE",
            currency_code="EUR"
        )
        self.retailer = Retailer.objects.create(
            account=self.account,
            legal_name="Nuboxed Germany GmbH",
            vat_number="DE123456789",
            status=Retailer.STATUS_APPROVED
        )

        # Create Order
        self.order = Order.objects.create(
            number="ORD-1001",
            customer=self.customer,
            retailer=self.retailer,
            status=Order.STATUS_PENDING,
            payment_status=Order.PAYMENT_PENDING,
            currency_code="EUR",
            subtotal_amount=Decimal("100.00"),
            discount_amount=Decimal("10.00"),
            tax_amount=Decimal("17.10"),  # 19% VAT on 90.00
            total_amount=Decimal("107.10"),
        )

        # Create Payment Gateways
        self.stripe_gateway = PaymentGateway.objects.create(
            code="stripe",
            name="Stripe",
            provider="StripeProvider",
            status=PaymentGateway.STATUS_ACTIVE,
            is_live=False,
            config={"publishable_key": "pk_test", "secret_key": "sk_test"}
        )
        self.paypal_gateway = PaymentGateway.objects.create(
            code="paypal",
            name="PayPal",
            provider="PayPalProvider",
            status=PaymentGateway.STATUS_ACTIVE,
            is_live=False
        )

    def test_wallet_creation_and_balance_modification(self):
        # 1. Get or create wallet
        wallet = get_or_create_wallet(self.retailer, "retailer", "EUR")
        self.assertEqual(wallet.balance, Decimal("0.00"))
        self.assertEqual(wallet.currency, "EUR")

        # 2. Modify balance (deposit)
        modify_wallet_balance(
            wallet=wallet,
            amount=Decimal("150.00"),
            transaction_type=WalletTransaction.TYPE_DEPOSIT,
            reference="dep_123",
            description="Initial deposit"
        )
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("150.00"))

        # 3. Modify balance (withdrawal)
        modify_wallet_balance(
            wallet=wallet,
            amount=Decimal("-50.00"),
            transaction_type=WalletTransaction.TYPE_WITHDRAWAL,
            reference="wit_123",
            description="Withdrawal test"
        )
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("100.00"))

        # 4. Check audit logs
        audit_logs = FinancialAuditLog.objects.filter(target_id=str(wallet.id))
        self.assertEqual(audit_logs.count(), 2)
        self.assertTrue(any("150" in log.description for log in audit_logs))

    def test_payment_transaction_lifecycle(self):
        # 1. Record payment transaction (Success/Captured)
        tx = record_payment_transaction(
            order=self.order,
            gateway=self.stripe_gateway,
            amount=Decimal("107.10"),
            currency="EUR",
            status=PaymentTransaction.STATUS_CAPTURED,
            gateway_transaction_id="ch_stripe_12345",
            actor=self.customer
        )

        self.assertEqual(tx.status, PaymentTransaction.STATUS_CAPTURED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PAYMENT_PAID)

        # 2. Check gateway charges created (Stripe: 2.9% + 0.30)
        gateway_charges = GatewayCharges.objects.get(payment_transaction=tx)
        expected_fee = ((Decimal("107.10") * Decimal("0.029")) + Decimal("0.30")).quantize(Decimal("0.01"))
        self.assertEqual(gateway_charges.charge_amount, expected_fee)

        # 3. Check Platform Commission created (10%)
        commission = PlatformCommission.objects.get(order=self.order)
        self.assertEqual(commission.commission_amount, Decimal("10.71"))

        # 4. Check Retailer Wallet credited net (107.10 - commission - fee)
        wallet = Wallet.objects.get(retailer=self.retailer)
        expected_net = Decimal("107.10") - Decimal("10.71") - expected_fee
        self.assertEqual(wallet.balance, expected_net)

        # 5. Check Invoice generated and marked Paid
        invoice = Invoice.objects.get(order=self.order)
        self.assertEqual(invoice.status, Invoice.STATUS_PAID)
        self.assertEqual(invoice.total_amount, Decimal("107.10"))
        self.assertEqual(invoice.tax_type, Invoice.TAX_TYPE_VAT)

    def test_refund_transaction(self):
        # Setup captured payment
        tx = record_payment_transaction(
            order=self.order,
            gateway=self.stripe_gateway,
            amount=Decimal("107.10"),
            currency="EUR",
            status=PaymentTransaction.STATUS_CAPTURED,
            gateway_transaction_id="ch_stripe_12345",
            actor=self.customer
        )

        wallet = Wallet.objects.get(retailer=self.retailer)
        initial_balance = wallet.balance

        # Process partial refund
        refund_amount = Decimal("50.00")
        refund = process_refund(
            payment_transaction=tx,
            amount=refund_amount,
            reason="Customer return",
            actor=self.super_admin
        )

        self.assertEqual(refund.status, RefundTransaction.STATUS_COMPLETED)
        
        # Check wallet deduction (refund amount - commission reclaim)
        # refund reclaim from retailer = 50.00 - (50.00 * 10%) = 45.00
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, initial_balance - Decimal("45.00"))

        # Check credit note created
        credit_note = CreditNote.objects.get(invoice__order=self.order)
        self.assertEqual(credit_note.amount, Decimal("50.00"))
        self.assertEqual(credit_note.status, CreditNote.STATUS_ISSUED)

    def test_retailer_settlement_workflow(self):
        # 1. Credit wallet
        wallet = get_or_create_wallet(self.retailer, "retailer", "EUR")
        modify_wallet_balance(
            wallet=wallet,
            amount=Decimal("500.00"),
            transaction_type=WalletTransaction.TYPE_DEPOSIT,
            description="Sales credits"
        )

        # 2. Initiate settlement payout
        bank_details = {"iban": "DE89370400440532013000", "bic": "SOLODEM1XXX"}
        settlement = process_retailer_settlement(
            retailer=self.retailer,
            amount=Decimal("400.00"),
            currency="EUR",
            bank_details=bank_details,
            actor=self.retailer_user
        )

        self.assertEqual(settlement.status, RetailerSettlement.STATUS_PENDING)
        self.assertEqual(settlement.net_amount, Decimal("400.00"))
        
        # Wallet should be debited
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("100.00"))

        # 3. Complete settlement (released by Super Admin)
        complete_retailer_settlement(
            settlement=settlement,
            payout_reference="WIRE-REF-9999",
            actor=self.super_admin
        )

        settlement.refresh_from_db()
        self.assertEqual(settlement.status, RetailerSettlement.STATUS_COMPLETED)
        self.assertEqual(settlement.payout_reference, "WIRE-REF-9999")
        self.assertIsNotNone(settlement.paid_at)

    def test_api_endpoints_super_admin(self):
        self.client.force_authenticate(user=self.super_admin)

        # List gateways
        response = self.client.get("/api/v1/payments/gateways/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Create new gateway
        data = {
            "code": "razorpay",
            "name": "Razorpay",
            "provider": "RazorpayProvider",
            "status": "active",
            "is_live": False
        }
        response = self.client.post("/api/v1/payments/gateways/", data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # View audit logs (accessible only by admin)
        response = self.client.get("/api/v1/payments/audit-logs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_api_endpoints_unauthorized(self):
        # Non-admin user tries to create gateway
        self.client.force_authenticate(user=self.customer)
        data = {
            "code": "razorpay",
            "name": "Razorpay",
            "provider": "RazorpayProvider"
        }
        response = self.client.post("/api/v1/payments/gateways/", data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Non-admin tries to view audit logs
        response = self.client.get("/api/v1/payments/audit-logs/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
