from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status

from apps.accounts.models import Account, AccountMembership
from apps.retailers.models import Retailer
from apps.orders.models import Order, OrderItem
from apps.catalog.models import Product, Category
from apps.stores.models import Store
from apps.inventory.models import Warehouse, StockItem
from apps.payments.models import PaymentGateway, PaymentTransaction, Wallet
from apps.returns_app.models import ReturnRequest, ReturnItem, ReturnTimeline
from apps.notifications.models import Notification
from apps.returns_app.services import (
    create_return_request,
    review_return_request,
    schedule_return_pickup,
    complete_return_pickup,
    receive_at_warehouse,
    perform_qc_assessment,
    execute_restock_decision,
    approve_refund_amount,
    process_and_complete_refund,
)

User = get_user_model()


class ReturnsModuleTestCase(APITestCase):
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
        # Create membership to grant retailer permissions
        AccountMembership.objects.create(
            account=self.account,
            user=self.retailer_user,
            status="active"
        )

        # Create Warehouse
        self.warehouse = Warehouse.objects.create(
            retailer=self.retailer,
            name="Munich Warehouse",
            code="MUC-WH-01",
            is_default=True
        )

        # Create Store and Category
        self.store = Store.objects.create(
            retailer=self.retailer,
            name="Munich Store",
            slug="munich-store"
        )
        self.category = Category.objects.create(
            name="Electronics",
            slug="electronics"
        )

        # Create Product
        self.product = Product.objects.create(
            name="Smartphone X",
            sku="SP-X-100",
            price=Decimal("500.00"),
            retailer=self.retailer,
            store=self.store,
            category=self.category
        )

        # Create StockItem
        self.stock_item = StockItem.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            on_hand_quantity=10,
            reserved_quantity=0
        )

        # Create Order
        self.order = Order.objects.create(
            number="ORD-2001",
            customer=self.customer,
            retailer=self.retailer,
            status=Order.STATUS_CONFIRMED,
            payment_status=Order.PAYMENT_PAID,
            currency_code="EUR",
            subtotal_amount=Decimal("500.00"),
            tax_amount=Decimal("95.00"),
            total_amount=Decimal("595.00"),
        )
        self.order_item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            warehouse=self.warehouse,
            quantity=1,
            unit_price=Decimal("500.00"),
            tax_rate=Decimal("19.00"),
            tax_amount=Decimal("95.00"),
            line_total=Decimal("595.00"),
        )

        # Create Payment Gateways & Captured Transaction
        self.stripe_gateway = PaymentGateway.objects.create(
            code="stripe",
            name="Stripe",
            provider="StripeProvider",
            status=PaymentGateway.STATUS_ACTIVE,
            is_live=False
        )
        self.tx = PaymentTransaction.objects.create(
            transaction_number="TXN-9999",
            order=self.order,
            gateway=self.stripe_gateway,
            amount=Decimal("595.00"),
            currency="EUR",
            status=PaymentTransaction.STATUS_CAPTURED,
            gateway_transaction_id="ch_stripe_9999"
        )

    def test_full_return_refund_flow_and_rules(self):
        # 1. Customer Return Request
        items_data = [{"order_item_id": self.order_item.id, "quantity": 1}]
        return_req = create_return_request(
            order=self.order,
            items_data=items_data,
            reason="Item defective",
            customer=self.customer
        )

        self.assertEqual(return_req.status, ReturnRequest.STATUS_REQUESTED)
        self.assertEqual(return_req.items.count(), 1)
        self.assertEqual(return_req.timeline_entries.count(), 1)

        # Assert notifications sent
        self.assertTrue(Notification.objects.filter(user=self.customer, subject__contains="Received").exists())

        # 2. Review Request (Approve)
        review_return_request(
            return_request=return_req,
            approved=True,
            notes="Defect verified via description",
            reviewer=self.super_admin
        )
        return_req.refresh_from_db()
        self.assertEqual(return_req.status, ReturnRequest.STATUS_APPROVED)
        self.assertEqual(return_req.timeline_entries.count(), 2)

        # 3. Schedule Return Pickup
        schedule_return_pickup(
            return_request=return_req,
            carrier="DHL Express",
            tracking_number="DHL-RET-8888",
            date=timezone.now().date() + timezone.timedelta(days=1),
            address="Customer Munich Address",
            actor=self.retailer_user
        )
        return_req.refresh_from_db()
        self.assertEqual(return_req.status, ReturnRequest.STATUS_PICKUP_SCHEDULED)

        # 4. Complete Return Pickup
        complete_return_pickup(return_request=return_req, actor=self.retailer_user)
        return_req.refresh_from_db()
        self.assertEqual(return_req.status, ReturnRequest.STATUS_PICKUP_COMPLETED)

        # 5. Receive at Warehouse
        receive_at_warehouse(return_request=return_req, actor=self.super_admin)
        return_req.refresh_from_db()
        self.assertEqual(return_req.status, ReturnRequest.STATUS_QC_PENDING)

        # 6. Warehouse QC Assessment (Passed)
        return_item = return_req.items.first()
        qc_results = [{"return_item_id": return_item.id, "qc_status": "passed", "qc_note": "Packaging open but item intact."}]
        perform_qc_assessment(return_request=return_req, qc_results=qc_results, actor=self.super_admin)
        return_req.refresh_from_db()
        self.assertEqual(return_req.status, ReturnRequest.STATUS_QC_PASSED)

        # 7. Restock Decision
        # Verify initial inventory count (10)
        self.stock_item.refresh_from_db()
        self.assertEqual(self.stock_item.on_hand_quantity, 10)

        restock_decisions = [{"return_item_id": return_item.id, "restock_decision": "restocked"}]
        execute_restock_decision(return_request=return_req, restock_decisions=restock_decisions, actor=self.super_admin)

        # Verify stock increased by 1 only after QC approval and restocking execution
        self.stock_item.refresh_from_db()
        self.assertEqual(self.stock_item.on_hand_quantity, 11)

        # 8. Approve Refund Amount (Full Refund)
        approve_refund_amount(return_request=return_req, refund_amount=Decimal("595.00"), actor=self.retailer_user)
        return_req.refresh_from_db()
        self.assertEqual(return_req.status, ReturnRequest.STATUS_REFUND_APPROVED)

        # 9. Process and Complete Refund
        process_and_complete_refund(return_request=return_req, actor=self.super_admin)
        return_req.refresh_from_db()
        self.assertEqual(return_req.status, ReturnRequest.STATUS_COMPLETED)

        # Check PaymentTransaction status updated to refunded
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.status, PaymentTransaction.STATUS_REFUNDED)

    def test_api_returns_workflow_permissions(self):
        self.client.force_authenticate(user=self.customer)

        # File return request via API
        data = {
            "order_id": str(self.order.id),
            "items": [{"order_item_id": str(self.order_item.id), "quantity": 1}],
            "reason": "Wrong size"
        }
        response = self.client.post("/api/v1/returns/requests/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return_id = response.data["id"]

        # Customer tries to review/approve their own return request -> should be Forbidden
        review_data = {"approved": True, "notes": "Sure"}
        response = self.client.post(f"/api/v1/returns/requests/{return_id}/review/", review_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Retailer reviews and approves
        self.client.force_authenticate(user=self.retailer_user)
        response = self.client.post(f"/api/v1/returns/requests/{return_id}/review/", review_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], ReturnRequest.STATUS_APPROVED)
