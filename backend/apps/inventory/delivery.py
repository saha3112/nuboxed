from datetime import timedelta
from decimal import Decimal
from math import atan2, cos, radians, sin, sqrt
import re

from django.db.models import Q
from django.utils import timezone

from apps.inventory.models import (
    CategoryDeliveryRule,
    DeliveryLocation,
    ProductDeliveryRule,
)
from apps.users.models import UserAddress

SESSION_LOCATION_KEY = "customer_delivery_location"


def normalize_postal_code(value):
    if not value:
        return ""
    return "".join(char for char in str(value).strip().upper() if char.isalnum())


def split_postal_codes(value):
    """Read exact or prefix coverage stored with common separators."""
    if not value:
        return []
    return [
        normalize_postal_code(item)
        for item in re.split(r"[,;\n]+", str(value))
        if normalize_postal_code(item)
    ]


def parse_decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def haversine_distance_km(lat1, lng1, lat2, lng2):
    radius_km = 6371.0
    delta_lat = radians(float(lat2) - float(lat1))
    delta_lng = radians(float(lng2) - float(lng1))
    lat1_rad = radians(float(lat1))
    lat2_rad = radians(float(lat2))
    arc = (
        sin(delta_lat / 2) ** 2
        + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lng / 2) ** 2
    )
    return 2 * radius_km * atan2(sqrt(arc), sqrt(1 - arc))


def build_location_payload(pincode="", latitude=None, longitude=None, source="manual", label=""):
    payload = {"source": source}
    normalized = normalize_postal_code(pincode)
    if normalized:
        payload["pincode"] = normalized
    lat = parse_decimal(latitude)
    lng = parse_decimal(longitude)
    if lat is not None and lng is not None:
        payload["latitude"] = str(lat)
        payload["longitude"] = str(lng)
    if label:
        payload["label"] = label
    return payload


def get_default_user_address(user):
    if not getattr(user, "is_authenticated", False):
        return None
    return user.addresses.filter(is_active=True, is_default=True).first() or user.addresses.filter(
        is_active=True
    ).first()


def get_request_location_payload(request):
    direct_pincode = normalize_postal_code(request.GET.get("pincode") or request.POST.get("pincode"))
    direct_latitude = parse_decimal(request.GET.get("latitude") or request.POST.get("latitude"))
    direct_longitude = parse_decimal(request.GET.get("longitude") or request.POST.get("longitude"))
    if direct_pincode or (direct_latitude is not None and direct_longitude is not None):
        return build_location_payload(
            pincode=direct_pincode,
            latitude=direct_latitude,
            longitude=direct_longitude,
            source="manual",
            label=direct_pincode or "Detected location",
        )

    session_payload = request.session.get(SESSION_LOCATION_KEY)
    if session_payload:
        return session_payload

    address = get_default_user_address(request.user)
    if address:
        return build_location_payload(
            pincode=address.postal_code,
            latitude=address.latitude,
            longitude=address.longitude,
            source="saved_address",
            label=address.postal_code,
        )
    return {}


def set_request_location(request, pincode="", latitude=None, longitude=None, source="manual", label=""):
    payload = build_location_payload(
        pincode=pincode,
        latitude=latitude,
        longitude=longitude,
        source=source,
        label=label or pincode or "Detected location",
    )
    request.session[SESSION_LOCATION_KEY] = payload
    request.session.modified = True
    return payload


def clear_request_location(request):
    request.session.pop(SESSION_LOCATION_KEY, None)
    request.session.modified = True


def get_location_label(payload):
    if not payload:
        return "Set pincode"
    return payload.get("label") or payload.get("pincode") or "Detected location"


def _delivery_locations_queryset(product, warehouse=None):
    queryset = DeliveryLocation.objects.filter(retailer=product.retailer, is_active=True)
    queryset = queryset.filter(Q(store=product.store) | Q(store__isnull=True))
    if warehouse is not None:
        queryset = queryset.filter(Q(warehouse=warehouse) | Q(warehouse__isnull=True))
    return queryset.order_by("priority", "name")


def _match_delivery_location(product, warehouse=None, pincode="", latitude=None, longitude=None):
    normalized = normalize_postal_code(pincode)
    latitude = parse_decimal(latitude)
    longitude = parse_decimal(longitude)
    for location in _delivery_locations_queryset(product, warehouse=warehouse):
        exact_codes = split_postal_codes(location.postal_code)
        prefix_codes = split_postal_codes(location.postal_code_prefix)
        if normalized:
            if normalized in exact_codes:
                return location, 3
            if any(prefix and normalized.startswith(prefix) for prefix in prefix_codes):
                return location, 2
        if (
            latitude is not None
            and longitude is not None
            and location.latitude is not None
            and location.longitude is not None
            and location.service_radius_km
        ):
            distance = haversine_distance_km(
                latitude,
                longitude,
                location.latitude,
                location.longitude,
            )
            if distance <= location.service_radius_km:
                return location, 1
    return None, 0


def _get_category_rule(product):
    exact = CategoryDeliveryRule.objects.filter(
        retailer=product.retailer,
        category=product.category,
        store=product.store,
        is_active=True,
    ).first()
    if exact:
        return exact
    return CategoryDeliveryRule.objects.filter(
        retailer=product.retailer,
        category=product.category,
        store__isnull=True,
        is_active=True,
    ).first()


def _get_product_rule(product, warehouse=None):
    exact = None
    if warehouse is not None:
        exact = ProductDeliveryRule.objects.filter(
            retailer=product.retailer,
            product=product,
            warehouse=warehouse,
            is_active=True,
        ).first()
    if exact:
        return exact
    return ProductDeliveryRule.objects.filter(
        retailer=product.retailer,
        product=product,
        warehouse__isnull=True,
        is_active=True,
    ).first()


def _add_delivery_days(start_date, days):
    current = start_date
    return current + timedelta(days=max(days, 0))


def _pick_candidate_stock_items(product):
    stock_items = list(
        product.stock_items.select_related("warehouse", "warehouse__store").all()
    )
    if not stock_items:
        return []
    available = [item for item in stock_items if item.available_quantity > 0]
    if available:
        return sorted(
            available,
            key=lambda item: (
                item.warehouse.is_default,
                item.available_quantity,
            ),
            reverse=True,
        )
    return sorted(stock_items, key=lambda item: item.warehouse.is_default, reverse=True)


def estimate_product_delivery(product, location_payload=None):
    payload = location_payload or {}
    pincode = normalize_postal_code(payload.get("pincode"))
    latitude = parse_decimal(payload.get("latitude"))
    longitude = parse_decimal(payload.get("longitude"))
    stock_items = _pick_candidate_stock_items(product)
    configured_locations = DeliveryLocation.objects.filter(retailer=product.retailer, is_active=True).exists()

    selected_stock = stock_items[0] if stock_items else None
    selected_warehouse = selected_stock.warehouse if selected_stock else None
    selected_location = None
    selected_match_score = 0

    for stock_item in stock_items:
        location, match_score = _match_delivery_location(
            product,
            warehouse=stock_item.warehouse,
            pincode=pincode,
            latitude=latitude,
            longitude=longitude,
        )
        if match_score > selected_match_score:
            selected_location = location
            selected_warehouse = stock_item.warehouse
            selected_stock = stock_item
            selected_match_score = match_score
        if match_score == 3:
            break

    if selected_warehouse is None and product.store.warehouses.exists():
        selected_warehouse = product.store.warehouses.order_by("-is_default", "name").first()

    if selected_warehouse and selected_location is None:
        selected_location, selected_match_score = _match_delivery_location(
            product,
            warehouse=selected_warehouse,
            pincode=pincode,
            latitude=latitude,
            longitude=longitude,
        )

    if configured_locations and (pincode or latitude is not None) and selected_location is None:
        return {
            "is_serviceable": False,
            "is_precise": True,
            "location_payload": payload,
            "label": f"Delivery unavailable for {pincode or 'this location'}",
            "date_label": "Unavailable",
            "warehouse": selected_warehouse,
            "delivery_days": None,
            "handling_days": None,
            "estimated_date": None,
        }

    product_rule = _get_product_rule(product, warehouse=selected_warehouse)
    category_rule = _get_category_rule(product)
    transit_days = (
        product_rule.delivery_days
        if product_rule
        else category_rule.delivery_days
        if category_rule
        else selected_location.delivery_days
        if selected_location
        else getattr(selected_warehouse, "delivery_days", None)
        or product.store.average_delivery_days
        or 3
    )
    handling_days = (
        getattr(selected_warehouse, "handling_time_days", 0)
        + (selected_location.handling_time_days if selected_location else 0)
    )
    total_days = transit_days + handling_days
    estimated_date = _add_delivery_days(timezone.localdate(), total_days)
    zone_name = selected_location.name if selected_location else "standard delivery area"
    date_label = estimated_date.strftime("%d %b %Y")
    return {
        "is_serviceable": True,
        "is_precise": bool(pincode or latitude is not None or selected_location),
        "location_payload": payload,
        "label": f"Estimated delivery by {date_label}",
        "date_label": date_label,
        "zone_name": zone_name,
        "warehouse": selected_warehouse,
        "stock_item": selected_stock,
        "delivery_days": transit_days,
        "handling_days": handling_days,
        "estimated_date": estimated_date,
        "available_quantity": selected_stock.available_quantity if selected_stock else 0,
    }


def resolve_geolocation_label(latitude, longitude):
    latitude = parse_decimal(latitude)
    longitude = parse_decimal(longitude)
    if latitude is None or longitude is None:
        return ""
    for location in DeliveryLocation.objects.filter(
        is_active=True,
        latitude__isnull=False,
        longitude__isnull=False,
        service_radius_km__gt=0,
    ).order_by("priority", "name"):
        distance = haversine_distance_km(latitude, longitude, location.latitude, location.longitude)
        if distance <= location.service_radius_km:
            return location.postal_code or location.name
    return "Detected location"


def serialize_delivery_context(payload):
    if not payload:
        return {
            "pincode": "",
            "source": "",
            "label": "Set pincode",
            "latitude": "",
            "longitude": "",
        }
    return {
        "pincode": payload.get("pincode", ""),
        "source": payload.get("source", ""),
        "label": get_location_label(payload),
        "latitude": payload.get("latitude", ""),
        "longitude": payload.get("longitude", ""),
    }
