from django.contrib import admin

from .models import (
    CategoryDeliveryRule,
    DeliveryHoliday,
    DeliveryLocation,
    LowStockAlert,
    OfflineSale,
    ProductDeliveryRule,
    StockAdjustment,
    StockItem,
    StockLedger,
    StockReservation,
    Warehouse,
)


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "store",
        "country_code",
        "delivery_days",
        "handling_time_days",
        "is_default",
        "is_active",
    )
    search_fields = ("name", "code", "city")


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ("product", "variant", "warehouse", "on_hand_quantity", "reserved_quantity", "available_quantity", "low_stock_threshold")
    search_fields = ("product__name", "variant__name", "warehouse__name")


admin.site.register(StockLedger)
admin.site.register(StockReservation)
admin.site.register(StockAdjustment)
admin.site.register(OfflineSale)
admin.site.register(LowStockAlert)


@admin.register(DeliveryLocation)
class DeliveryLocationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "retailer",
        "store",
        "warehouse",
        "postal_code",
        "postal_code_prefix",
        "delivery_days",
        "handling_time_days",
        "priority",
        "is_active",
    )
    list_filter = ("country_code", "retailer")
    search_fields = ("name", "postal_code", "postal_code_prefix", "city", "state")


@admin.register(CategoryDeliveryRule)
class CategoryDeliveryRuleAdmin(admin.ModelAdmin):
    list_display = ("category", "retailer", "store", "delivery_days", "is_active")
    list_filter = ("retailer", "store")
    search_fields = ("category__name",)


@admin.register(ProductDeliveryRule)
class ProductDeliveryRuleAdmin(admin.ModelAdmin):
    list_display = ("product", "retailer", "warehouse", "delivery_days", "is_active")
    list_filter = ("retailer", "warehouse")
    search_fields = ("product__name", "product__sku")


@admin.register(DeliveryHoliday)
class DeliveryHolidayAdmin(admin.ModelAdmin):
    list_display = ("name", "retailer", "store", "warehouse", "holiday_date", "is_active")
    list_filter = ("retailer", "holiday_date")
    search_fields = ("name",)
