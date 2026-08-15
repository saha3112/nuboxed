from django.urls import path

from .views import (
    CategoryDeliveryRuleListCreateView,
    DeliveryEstimateView,
    DeliveryLocationListCreateView,
    LowStockAlertListView,
    OfflineSaleListCreateView,
    ProductDeliveryRuleListCreateView,
    StockAdjustmentCreateView,
    StockItemListView,
    StockLedgerListView,
    WarehouseListCreateView,
)

urlpatterns = [
    path("warehouses/", WarehouseListCreateView.as_view(), name="inventory-warehouses"),
    path("delivery-locations/", DeliveryLocationListCreateView.as_view(), name="inventory-delivery-locations"),
    path("category-delivery-rules/", CategoryDeliveryRuleListCreateView.as_view(), name="inventory-category-delivery-rules"),
    path("product-delivery-rules/", ProductDeliveryRuleListCreateView.as_view(), name="inventory-product-delivery-rules"),
    path("stock-items/", StockItemListView.as_view(), name="inventory-stock-items"),
    path("ledger/", StockLedgerListView.as_view(), name="inventory-ledger"),
    path("adjustments/", StockAdjustmentCreateView.as_view(), name="inventory-adjustments"),
    path("offline-sales/", OfflineSaleListCreateView.as_view(), name="inventory-offline-sales"),
    path("low-stock-alerts/", LowStockAlertListView.as_view(), name="inventory-low-stock-alerts"),
    path("eta/estimate/", DeliveryEstimateView.as_view(), name="inventory-delivery-estimate"),
]
