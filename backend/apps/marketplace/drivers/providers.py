from typing import Dict, Any
from django.utils import timezone
from datetime import timedelta
from apps.marketplace.drivers.base import BaseMarketplaceDriver


class MockBaseDriver(BaseMarketplaceDriver):
    """
    Staging driver that simulates integration calls for validation and testing.
    """

    def refresh_token(self) -> Dict[str, Any]:
        self.connection.access_token = f"mock_access_token_{self.connection.connector.code}_{timezone.now().timestamp()}"
        self.connection.token_expires_at = timezone.now() + timedelta(hours=2)
        self.connection.save()
        return {"status": "refreshed", "expires_at": self.connection.token_expires_at}

    def sync_products(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        return {
            "status": "success",
            "synced_count": len(payload.get("items", [])) if payload else 1,
            "provider": self.__class__.__name__
        }

    def sync_prices(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        return {
            "status": "success",
            "updated_prices": len(payload.get("prices", [])) if payload else 1,
            "provider": self.__class__.__name__
        }

    def sync_stock(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        return {
            "status": "success",
            "updated_stock": len(payload.get("stock", [])) if payload else 1,
            "provider": self.__class__.__name__
        }

    def import_orders(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        return {
            "status": "success",
            "imported_orders": [
                {
                    "external_order_id": f"EXT-{self.connection.connector.code.upper()}-12345",
                    "status": "unfulfilled",
                    "amount": 250.00,
                    "currency": "EUR"
                }
            ],
            "provider": self.__class__.__name__
        }

    def sync_returns(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        return {
            "status": "success",
            "synced_returns": 1,
            "provider": self.__class__.__name__
        }

    def sync_refunds(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        return {
            "status": "success",
            "synced_refunds": 1,
            "provider": self.__class__.__name__
        }

    def sync_settlements(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        return {
            "status": "success",
            "payout_amount": 1250.00,
            "currency": "EUR",
            "provider": self.__class__.__name__
        }

    def handle_webhook(self, headers: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "processed",
            "event": payload.get("event_type", "unknown"),
            "provider": self.__class__.__name__
        }


class AmazonDriver(MockBaseDriver):
    pass


class FlipkartDriver(MockBaseDriver):
    pass


class MyntraDriver(MockBaseDriver):
    pass


class ShopifyDriver(MockBaseDriver):
    pass


class WooCommerceDriver(MockBaseDriver):
    pass


class EbayDriver(MockBaseDriver):
    pass


class BolDriver(MockBaseDriver):
    pass


class KauflandDriver(MockBaseDriver):
    pass


# Registry Mapping
DRIVER_REGISTRY = {
    "amazon": AmazonDriver,
    "flipkart": FlipkartDriver,
    "myntra": MyntraDriver,
    "shopify": ShopifyDriver,
    "woocommerce": WooCommerceDriver,
    "ebay": EbayDriver,
    "bol.com": BolDriver,
    "kaufland": KauflandDriver,
}


def get_driver(connection) -> BaseMarketplaceDriver:
    connector_type = connection.connector.connector_type.lower()
    driver_class = DRIVER_REGISTRY.get(connector_type)
    if not driver_class:
        # Extensible fallback for future connectors
        return MockBaseDriver(connection)
    return driver_class(connection)
