from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status

from apps.accounts.models import Account, AccountMembership
from apps.retailers.models import Retailer
from apps.marketplace.models import (
    MarketplaceConnector,
    MarketplaceConnection,
    MarketplaceSyncJob,
    MarketplaceConflictLog,
    MarketplaceWebhookEvent
)
from apps.marketplace.services import (
    configure_connector,
    create_connection,
    enqueue_sync_job,
    process_sync_job,
    resolve_conflict,
    receive_webhook_event,
    process_webhook_event,
    cron_fallback_sync,
    get_sync_dashboard_stats
)

User = get_user_model()


class MarketplaceConnectorTestCase(APITestCase):
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
            name="Merchant Account",
            slug="merchant-account",
            owner=self.retailer_user,
            country_code="DE",
            currency_code="EUR"
        )
        self.retailer = Retailer.objects.create(
            account=self.account,
            legal_name="Nuboxed Retailer GmbH",
            status=Retailer.STATUS_APPROVED
        )
        AccountMembership.objects.create(
            account=self.account,
            user=self.retailer_user,
            status="active"
        )

        # Configured Connector
        self.connector = MarketplaceConnector.objects.create(
            code="shopify",
            name="Shopify Connector",
            connector_type="Shopify",
            status=MarketplaceConnector.STATUS_ACTIVE
        )

    def test_permissions_rules_only_super_admin_can_configure(self):
        # Retailer user tries to configure/create a connector -> Forbidden
        self.client.force_authenticate(user=self.retailer_user)
        conn_data = {
            "code": "amazon",
            "name": "Amazon SP-API",
            "connector_type": "Amazon",
            "status": "active"
        }
        response = self.client.post("/api/v1/marketplace/connectors/", conn_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Retailer user tries to create a connection -> Forbidden
        connection_data = {
            "connector": str(self.connector.id),
            "retailer": str(self.retailer.id),
            "name": "Shopify Account Connection",
            "credentials": {"shop_url": "test.myshopify.com", "api_key": "123"}
        }
        response = self.client.post("/api/v1/marketplace/connections/", connection_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Super admin configures a connector -> Success
        self.client.force_authenticate(user=self.super_admin)
        response = self.client.post("/api/v1/marketplace/connectors/", conn_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["code"], "amazon")

        # Super admin creates a connection -> Success
        response = self.client.post("/api/v1/marketplace/connections/", connection_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Shopify Account Connection")

    def test_sync_job_processing_and_retry_queue(self):
        # Create a connection
        connection = create_connection(
            connector=self.connector,
            name="Shopify Test Store",
            credentials={"api_key": "test_key", "secret": "test_secret"},
            retailer=self.retailer
        )

        # Enqueue a sync job
        job = enqueue_sync_job(
            connection=connection,
            job_type=MarketplaceSyncJob.TYPE_PRODUCT_SYNC,
            direction=MarketplaceSyncJob.DIRECTION_OUTBOUND,
            payload={"items": [{"sku": "SKU-A", "price": 100.00}]}
        )

        self.assertEqual(job.status, MarketplaceSyncJob.STATUS_PENDING)
        self.assertEqual(job.retry_count, 0)

        # Process job via service
        job = process_sync_job(job)
        self.assertEqual(job.status, MarketplaceSyncJob.STATUS_COMPLETED)
        self.assertEqual(job.result["provider"], "ShopifyDriver")
        self.assertEqual(job.result["synced_count"], 1)

    def test_conflict_resolution_workflow(self):
        connection = create_connection(
            connector=self.connector,
            name="Shopify Store",
            credentials={},
            retailer=self.retailer
        )

        # Log a conflict
        conflict = MarketplaceConflictLog.objects.create(
            connection=connection,
            entity_type="product",
            entity_id="prod_01",
            external_id="ext_prod_01",
            local_data={"price": 10.00},
            external_data={"price": 12.00},
            conflict_reason="Price mismatch"
        )

        # Resolve using external strategy
        self.client.force_authenticate(user=self.super_admin)
        resolve_data = {"resolution_strategy": "use_external"}
        response = self.client.post(f"/api/v1/marketplace/conflicts/{conflict.id}/resolve/", resolve_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_resolved"])
        self.assertEqual(response.data["resolution_strategy"], "use_external")

        # Verify a pull/sync job was enqueued as a result
        self.assertTrue(MarketplaceSyncJob.objects.filter(
            connection=connection,
            job_type=MarketplaceSyncJob.TYPE_PRODUCT_SYNC,
            direction=MarketplaceSyncJob.DIRECTION_INBOUND
        ).exists())

    def test_webhook_listener_and_cron_fallback(self):
        connection = create_connection(
            connector=self.connector,
            name="Shopify Active Connection",
            credentials={},
            retailer=self.retailer
        )

        # Webhook event post -> processed
        webhook_payload = {"event_type": "orders/create", "order_id": "999"}
        response = self.client.post(
            f"/api/v1/marketplace/webhooks/shopify/",
            webhook_payload,
            format="json",
            HTTP_X_SHOPIFY_TOPIC="orders/create"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "processed")

        # Trigger cron fallback manually
        self.client.force_authenticate(user=self.super_admin)
        response = self.client.post("/api/v1/marketplace/cron-fallback/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertGreater(len(response.data), 0)

        # Dashboard stats check
        response = self.client.get("/api/v1/marketplace/dashboard/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("sync_jobs", response.data)
        self.assertIn("connections", response.data)
