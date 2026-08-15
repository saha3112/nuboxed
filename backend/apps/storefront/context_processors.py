from django.db.models import Q
from django.core.cache import cache
from apps.catalog.models import Brand, Category, Product
from apps.inventory.delivery import get_request_location_payload, serialize_delivery_context, split_postal_codes, normalize_postal_code
from apps.inventory.models import DeliveryLocation
from apps.orders.models import Cart
from apps.stores.models import Store


def storefront_navigation(request):
    session_cart = request.session.get("cart", {})
    wishlist = request.session.get("wishlist", [])
    nav_catalog = cache.get("storefront-navigation-catalog-v1")
    if nav_catalog is None:
        primary_store = Store.objects.filter(status=Store.STATUS_ACTIVE, is_active=True).order_by("name").first()
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
        active_store_links = list(Store.objects.filter(status=Store.STATUS_ACTIVE, is_active=True).order_by("name")[:30])
        nav_catalog = {
            "primary_store": primary_store,
            "device_categories": nav_device_categories,
            "store_links": active_store_links,
        }
        cache.set("storefront-navigation-catalog-v1", nav_catalog, 60)
    primary_store = nav_catalog["primary_store"]
    nav_device_categories = nav_catalog["device_categories"]
    active_store_links = nav_catalog["store_links"]
    location_payload = get_request_location_payload(request)
    location_pincode = normalize_postal_code(location_payload.get("pincode"))
    location_city = normalize_postal_code(location_payload.get("city"))
    if location_pincode or location_city:
        # Navigation is cached, but store availability is customer-location
        # specific. Resolve the menu links per request using the same saved
        # Delivery Location coverage rules as the Stores page.
        all_active_stores = list(Store.objects.filter(status=Store.STATUS_ACTIVE, is_active=True).order_by("name"))
        store_ids = {store.id for store in all_active_stores}
        configured_locations = list(
            DeliveryLocation.objects.filter(is_active=True, store_id__in=store_ids)
            .select_related("store")
        )
        matched_store_ids = set()
        if configured_locations:
            for location in configured_locations:
                exact_codes = split_postal_codes(location.postal_code)
                prefix_codes = split_postal_codes(location.postal_code_prefix)
                location_city_value = normalize_postal_code(location.city)
                if location_pincode and (
                    location_pincode in exact_codes
                    or any(location_pincode.startswith(prefix) for prefix in prefix_codes if prefix)
                ):
                    matched_store_ids.add(location.store_id)
                elif location_city and location_city_value == location_city:
                    matched_store_ids.add(location.store_id)
            active_store_links = [store for store in all_active_stores if store.id in matched_store_ids]
        else:
            # Before a retailer configures coverage rules, retain the useful
            # store-address fallback for the navigation menu.
            active_store_links = [
                store for store in all_active_stores
                if (
                    location_pincode
                    and normalize_postal_code(store.postal_code) == location_pincode
                ) or (
                    location_city
                    and normalize_postal_code(store.city) == location_city
                )
            ]
    active_store_links = active_store_links[:30]
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
    nav_cart_currency_code = (nav_cart.currency_code if nav_cart else "EUR") or "EUR"
    return {
        "nav_store_links": active_store_links[:6],
        "nav_store_more_links": active_store_links[6:],
        "nav_device_categories": nav_device_categories,
        "nav_cart_count": nav_cart_count,
        "nav_cart_items": nav_cart_items,
        "nav_cart_total": nav_cart_total,
        "nav_cart_currency_code": nav_cart_currency_code,
        "nav_wishlist_count": len(wishlist),
        "nav_compare_count": len(request.session.get("compare_list", [])),
        "compare_list": request.session.get("compare_list", []),
        "wishlist": request.session.get("wishlist", []),
        "nav_primary_store": primary_store,
        "nav_delivery_location": serialize_delivery_context(get_request_location_payload(request)),
    }
