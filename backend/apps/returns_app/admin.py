from django.contrib import admin
from apps.returns_app.models import ReturnRequest, ReturnItem, ReturnTimeline


class ReturnItemInline(admin.TabularInline):
    model = ReturnItem
    extra = 0


class ReturnTimelineInline(admin.TabularInline):
    model = ReturnTimeline
    extra = 0
    readonly_fields = ("occurred_at",)


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ("return_number", "order", "customer", "retailer", "status", "refund_amount", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("return_number", "order__number", "customer__email", "retailer__legal_name")
    inlines = [ReturnItemInline, ReturnTimelineInline]
    readonly_fields = ("return_number", "reviewed_at")


@admin.register(ReturnItem)
class ReturnItemAdmin(admin.ModelAdmin):
    list_display = ("return_request", "order_item", "quantity", "qc_status", "restock_decision", "restocked_at")
    list_filter = ("qc_status", "restock_decision")
    search_fields = ("return_request__return_number", "order_item__product__name")


@admin.register(ReturnTimeline)
class ReturnTimelineAdmin(admin.ModelAdmin):
    list_display = ("return_request", "status", "title", "actor", "occurred_at")
    list_filter = ("status", "occurred_at")
    search_fields = ("return_request__return_number", "title")
