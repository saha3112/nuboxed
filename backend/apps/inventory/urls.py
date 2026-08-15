from django.urls import path

from .views import (
    CategoryDeliveryRuleCreateView,
    DeliveryLocationCreateView,
    DeliveryLocationActionView,
    DeliveryLocationUpdateView,
    DeliveryLocationsRulesView,
    DeliveryPostalLookupView,
    InventoryDashboardView,
    OfflineSaleCreateView,
    OfflineSaleOptionsView,
    OfflineSaleUpdateView,
    OfflineSaleActionView,
    OfflineSalesSettingsView,
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
    path("retailer/inventory/offline-sales/options/", OfflineSaleOptionsView.as_view(), name="offline-sale-options"),
    path("retailer/inventory/offline-sales/<uuid:pk>/edit/", OfflineSaleUpdateView.as_view(), name="offline-sale-edit"),
    path("retailer/inventory/offline-sales/<uuid:pk>/<str:action>/", OfflineSaleActionView.as_view(), name="offline-sale-action"),
    path("retailer/inventory/offline-sales/settings/", OfflineSalesSettingsView.as_view(), name="offline-sales-settings"),
    path("retailer/inventory/delivery-locations/new/", DeliveryLocationCreateView.as_view(), name="delivery-location-create"),
    path("retailer/inventory/delivery-locations/", DeliveryLocationsRulesView.as_view(), name="delivery-locations"),
    path("retailer/inventory/delivery-locations/<uuid:pk>/edit/", DeliveryLocationUpdateView.as_view(), name="delivery-location-edit"),
    path("retailer/inventory/delivery-locations/<uuid:pk>/<str:action>/", DeliveryLocationActionView.as_view(), name="delivery-location-action"),
    path("retailer/inventory/delivery-locations/postal-lookup/", DeliveryPostalLookupView.as_view(), name="delivery-postal-lookup"),
    path("retailer/inventory/category-delivery/new/", CategoryDeliveryRuleCreateView.as_view(), name="category-delivery-create"),
    path("retailer/inventory/product-delivery/new/", ProductDeliveryRuleCreateView.as_view(), name="product-delivery-create"),
]
