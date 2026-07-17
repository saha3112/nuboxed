from django.contrib import admin

from .models import Cart, CartItem, Order, OrderItem, OrderTimeline


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "status", "subtotal_amount", "tax_amount", "shipping_amount", "total_amount", "updated_at")
    list_filter = ("status", "currency_code")
    search_fields = ("customer__email", "session_key", "coupon_code")
    inlines = [CartItemInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


class OrderTimelineInline(admin.TabularInline):
    model = OrderTimeline
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "customer",
        "retailer",
        "status",
        "payment_status",
        "shipping_postal_code",
        "total_amount",
        "placed_at",
    )
    list_filter = ("status", "payment_status", "shipping_country_code")
    search_fields = ("number", "customer__email", "shipping_postal_code")
    inlines = [OrderItemInline, OrderTimelineInline]
