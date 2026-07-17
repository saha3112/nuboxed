from django.db.models import Q
from apps.catalog.models import Brand, Category, Product
from apps.inventory.delivery import get_request_location_payload, serialize_delivery_context
from apps.orders.models import Cart
from apps.stores.models import Store


def storefront_navigation(request):
    session_cart = request.session.get("cart", {})
    wishlist = request.session.get("wishlist", [])
    primary_store = Store.objects.filter(status=Store.STATUS_ACTIVE, is_active=True).order_by("name").first()
    nav_cart_count = sum(item.get("quantity", 0) for item in session_cart.values())
    nav_cart = None
    nav_cart_items = []
    nav_cart_total = 0
    if request.user.is_authenticated:
        nav_cart = (
            Cart.objects.filter(customer=request.user, status=Cart.STATUS_OPEN, is_active=True)
            .prefetch_related("items__product__store", "items__product__media_items")
            .first()
        )
    elif request.session.session_key:
        nav_cart = (
            Cart.objects.filter(session_key=request.session.session_key, status=Cart.STATUS_OPEN, is_active=True)
            .prefetch_related("items__product__store", "items__product__media_items")
            .first()
        )
    if nav_cart:
        nav_cart_items = list(nav_cart.items.all()[:5])
        nav_cart_count = sum(item.quantity for item in nav_cart.items.all())
        nav_cart_total = nav_cart.total_amount
    nav_device_categories = list(
        Category.objects.filter(parent__isnull=True, is_active=True).filter(
            Q(products__isnull=False) | Q(children__products__isnull=False) | Q(children__children__products__isnull=False)
        ).distinct().order_by("sort_order", "name").prefetch_related("children", "children__children")[:12]
    )
    for device in nav_device_categories:
        for subcategory in device.children.all():
            descendant_ids = [subcategory.id, *subcategory.children.values_list("id", flat=True)]
            subcategory.nav_brands = list(
                Brand.objects.filter(
                    products__category_id__in=descendant_ids,
                    products__status=Product.STATUS_APPROVED,
                    products__is_active=True,
                    products__deleted_at__isnull=True,
                ).distinct().order_by("name")
            )

    return {
        "nav_store_links": Store.objects.filter(status=Store.STATUS_ACTIVE, is_active=True).order_by("name")[:12],
        "nav_device_categories": nav_device_categories,
        "nav_cart_count": nav_cart_count,
        "nav_cart_items": nav_cart_items,
        "nav_cart_total": nav_cart_total,
        "nav_wishlist_count": len(wishlist),
        "nav_compare_count": len(request.session.get("compare_list", [])),
        "compare_list": request.session.get("compare_list", []),
        "wishlist": request.session.get("wishlist", []),
        "nav_primary_store": primary_store,
        "nav_delivery_location": serialize_delivery_context(get_request_location_payload(request)),
    }
