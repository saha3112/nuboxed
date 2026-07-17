import logging
from abc import ABC, abstractmethod
from typing import Dict, Any

logger = logging.getLogger(__name__)

class BaseMarketplaceDriver(ABC):
    """
    Abstract Base Class representing the interface for all marketplace connectors.
    """

    def __init__(self, connection):
        self.connection = connection

    @abstractmethod
    def refresh_token(self) -> Dict[str, Any]:
        """
        Handles OAuth credentials refresh.
        """
        pass

    @abstractmethod
    def sync_products(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Pushes or pulls products.
        """
        pass

    @abstractmethod
    def sync_prices(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Pushes updated pricing.
        """
        pass

    @abstractmethod
    def sync_stock(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Pushes updated stock counts.
        """
        pass

    @abstractmethod
    def import_orders(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Pulls/imports orders.
        """
        pass

    @abstractmethod
    def sync_returns(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Pulls or pushes return requests.
        """
        pass

    @abstractmethod
    def sync_refunds(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Syncs refund updates.
        """
        pass

    @abstractmethod
    def sync_settlements(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Imports financial reports and settlements.
        """
        pass

    @abstractmethod
    def handle_webhook(self, headers: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes real-time inbound webhook updates.
        """
        pass
