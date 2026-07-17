from django.urls import path

from .views import (
    CategoryDeliveryRuleCreateView,
    DeliveryHolidayCreateView,
    DeliveryLocationCreateView,
    InventoryDashboardView,
    OfflineSaleCreateView,
    ProductDeliveryRuleCreateView,
    StockAdjustmentCreateView,
    WarehouseCreateView,
)

app_name = "inventory"

urlpatterns = [
    path("retailer/inventory/", InventoryDashboardView.as_view(), name="dashboard"),
    path("retailer/inventory/warehouses/new/", WarehouseCreateView.as_view(), name="warehouse-create"),
    path("retailer/inventory/adjustments/new/", StockAdjustmentCreateView.as_view(), name="adjustment-create"),
    path("retailer/inventory/offline-sales/new/", OfflineSaleCreateView.as_view(), name="offline-sale-create"),
    path("retailer/inventory/delivery-locations/new/", DeliveryLocationCreateView.as_view(), name="delivery-location-create"),
    path("retailer/inventory/category-delivery/new/", CategoryDeliveryRuleCreateView.as_view(), name="category-delivery-create"),
    path("retailer/inventory/product-delivery/new/", ProductDeliveryRuleCreateView.as_view(), name="product-delivery-create"),
    path("retailer/inventory/holidays/new/", DeliveryHolidayCreateView.as_view(), name="delivery-holiday-create"),
]
