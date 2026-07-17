from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.inventory.models import OfflineSale
from apps.orders.models import Order
from apps.orders.services import build_order_timeline
from apps.shipments.models import (
    CourierBooking,
    CourierCredential,
    CourierCountryServiceability,
    CourierPerformanceReport,
    CourierPickupSchedule,
    CourierPartner,
    CourierRule,
    CourierReturnPickup,
    CourierServiceabilityRule,
    CourierShipmentEvent,
    FulfillmentRecord,
    Shipment,
)
from apps.notifications.services import send_notification_event

FULFILLMENT_RULES = {
    Order.SOURCE_WEBSITE: {
        "flow": Order.FULFILLMENT_INTERNAL_COURIER,
        "mode": FulfillmentRecord.MODE_BOOK_COURIER,
        "courier_booking_required": True,
    },
    Order.SOURCE_AMAZON: {
        "flow": Order.FULFILLMENT_AMAZON,
        "mode": FulfillmentRecord.MODE_SYNC_ONLY,
        "courier_booking_required": False,
    },
    Order.SOURCE_FLIPKART: {
        "flow": Order.FULFILLMENT_FLIPKART,
        "mode": FulfillmentRecord.MODE_SYNC_ONLY,
        "courier_booking_required": False,
    },
    Order.SOURCE_EBAY: {
        "flow": Order.FULFILLMENT_EBAY,
        "mode": FulfillmentRecord.MODE_SYNC_ONLY,
        "courier_booking_required": False,
    },
    Order.SOURCE_SHOPIFY: {
        "flow": Order.FULFILLMENT_PLATFORM,
        "mode": FulfillmentRecord.MODE_SYNC_ONLY,
        "courier_booking_required": False,
    },
    Order.SOURCE_WOOCOMMERCE: {
        "flow": Order.FULFILLMENT_PLATFORM,
        "mode": FulfillmentRecord.MODE_SYNC_ONLY,
        "courier_booking_required": False,
    },
    Order.SOURCE_OFFLINE: {
        "flow": Order.FULFILLMENT_OFFLINE,
        "mode": FulfillmentRecord.MODE_OFFLINE,
        "courier_booking_required": False,
    },
}


def normalize_postal_code(value):
    if not value:
        return ""
    return "".join(char for char in str(value).strip().upper() if char.isalnum())


def resolve_order_fulfillment_rule(order):
    return FULFILLMENT_RULES.get(order.source_channel, FULFILLMENT_RULES[Order.SOURCE_WEBSITE])


def should_create_internal_courier_booking(order):
    rule = resolve_order_fulfillment_rule(order)
    return (
        rule["courier_booking_required"]
        and order.source_channel == Order.SOURCE_WEBSITE
        and order.fulfillment_flow == Order.FULFILLMENT_INTERNAL_COURIER
    )


def get_default_internal_courier_partner():
    rule = (
        CourierRule.objects.select_related("courier_partner")
        .filter(
            courier_partner__is_active=True,
            courier_partner__status__in=["active", "approved"],
            rule_type=CourierRule.RULE_BOOKING,
            is_enabled=True,
        )
        .order_by("priority", "courier_partner__name")
        .first()
    )
    if rule:
        return rule.courier_partner
    return (
        CourierPartner.objects.filter(is_active=True, status__in=["active", "approved"])
        .order_by("name")
        .first()
    )


def get_courier_credentials(courier_partner):
    return {
        credential.credential_type: credential.value
        for credential in courier_partner.credentials.filter(is_active=True)
    }


def get_primary_courier_partner(country_code=None):
    queryset = (
        CourierCountryServiceability.objects.select_related("courier_partner")
        .filter(is_active=True, is_serviceable=True)
        .order_by("courier_partner__name")
    )
    if country_code:
        specific = queryset.filter(country_code=country_code.upper()).first()
        if specific:
            return specific.courier_partner
    return queryset.first().courier_partner if queryset.first() else None


def _serviceability_base_queryset(courier_partner=None):
    queryset = CourierServiceabilityRule.objects.filter(is_active=True, serviceable=True)
    if courier_partner is not None:
        queryset = queryset.filter(courier_partner=courier_partner)
    return queryset.select_related("courier_partner", "store").order_by("priority", "courier_partner__name")


def check_courier_serviceability(*, postal_code, country_code, courier_partner=None, store=None):
    normalized_postal_code = normalize_postal_code(postal_code)
    country_code = (country_code or "").upper()
    queryset = _serviceability_base_queryset(courier_partner=courier_partner)
    if store is not None:
        queryset = queryset.filter(Q(store=store) | Q(store__isnull=True))

    best_match = None
    best_score = -1
    for rule in queryset:
        score = 0
        if rule.country_code and rule.country_code.upper() != country_code:
            continue
        if rule.postal_code and normalize_postal_code(rule.postal_code) == normalized_postal_code:
            score = 3
        elif rule.postal_code_prefix and normalized_postal_code.startswith(normalize_postal_code(rule.postal_code_prefix)):
            score = 2
        elif not rule.postal_code and not rule.postal_code_prefix:
            score = 1
        if score > best_score:
            best_match = rule
            best_score = score

    if best_match:
        return {
            "serviceable": best_match.serviceable,
            "pickup_available": best_match.pickup_available,
            "cod_available": best_match.cod_available,
            "handling_days": best_match.handling_time_days,
            "transit_days": best_match.transit_days,
            "courier_partner": best_match.courier_partner,
            "matched_rule": best_match,
            "country_code": country_code,
            "postal_code": normalized_postal_code,
        }

    country_rule = CourierCountryServiceability.objects.filter(
        is_active=True,
        courier_partner=courier_partner or get_primary_courier_partner(country_code),
        country_code=country_code,
    ).first()
    if country_rule:
        return {
            "serviceable": country_rule.is_serviceable,
            "pickup_available": country_rule.is_serviceable,
            "cod_available": country_rule.cod_available,
            "handling_days": 0,
            "transit_days": country_rule.max_transit_days,
            "courier_partner": country_rule.courier_partner,
            "matched_rule": None,
            "country_code": country_code,
            "postal_code": normalized_postal_code,
        }

    return {
        "serviceable": False,
        "pickup_available": False,
        "cod_available": False,
        "handling_days": 0,
        "transit_days": 0,
        "courier_partner": courier_partner,
        "matched_rule": None,
        "country_code": country_code,
        "postal_code": normalized_postal_code,
    }


def build_sync_only_note(order):
    return (
        f"{order.get_source_channel_display()} order is sync-only in CommerceOS. "
        "No internal courier booking will be created. Only order, stock, return, refund, settlement, and reports sync apply."
    )


def _ensure_fulfillment_record(order, rule):
    note = (
        "Internal marketplace fulfillment active."
        if rule["mode"] == FulfillmentRecord.MODE_BOOK_COURIER
        else build_sync_only_note(order)
        if rule["mode"] == FulfillmentRecord.MODE_SYNC_ONLY
        else "Offline fulfillment active."
    )
    fulfillment_record, _ = FulfillmentRecord.objects.get_or_create(
        order=order,
        defaults={
            "connector": order.marketplace_connector,
            "source_channel": order.source_channel,
            "flow_type": rule["flow"],
            "mode": rule["mode"],
            "status": FulfillmentRecord.STATUS_ACTIVE,
            "courier_booking_required": rule["courier_booking_required"],
            "stock_sync_enabled": True,
            "return_sync_enabled": True,
            "refund_sync_enabled": True,
            "settlement_sync_enabled": True,
            "report_sync_enabled": True,
            "note": note,
        },
    )
    return fulfillment_record


@transaction.atomic
def create_courier_shipment(order, courier_partner=None, actor=None):
    if not order.is_website_order:
        raise ValueError("Courier booking is only allowed for website orders.")
    if order.fulfillment_flow != Order.FULFILLMENT_INTERNAL_COURIER:
        raise ValueError("Courier booking requires internal courier fulfillment flow.")

    courier_partner = courier_partner or get_primary_courier_partner(order.shipping_country_code) or get_default_internal_courier_partner()
    if courier_partner is None:
        raise ValueError("No active courier partner configured for website order booking.")

    shipment = Shipment.objects.filter(order=order, flow_type=Order.FULFILLMENT_INTERNAL_COURIER).first()
    if not shipment:
        shipment = Shipment.objects.create(
            order=order,
            courier_partner=courier_partner,
            carrier=courier_partner.name,
            flow_type=Order.FULFILLMENT_INTERNAL_COURIER,
            booking_source="commerceos",
            tracking_number=f"INT-{uuid4().hex[:10].upper()}",
            status="pending",
            tracking_status="pending",
            sync_only=False,
            note="Shipment created for website order internal courier flow.",
        )
    else:
        shipment.courier_partner = courier_partner
        shipment.carrier = courier_partner.name
        shipment.save(update_fields=["courier_partner", "carrier", "updated_at"])

    booking = CourierBooking.objects.filter(order=order, shipment=shipment).first()
    if not booking:
        booking = CourierBooking.objects.create(
            order=order,
            shipment=shipment,
            courier_partner=courier_partner,
            booking_reference=f"CB-{uuid4().hex[:12].upper()}",
            status=CourierBooking.STATUS_PENDING,
            requested_payload={
                "order_number": order.number,
                "postal_code": order.shipping_postal_code,
                "country_code": order.shipping_country_code,
                "total_amount": str(order.total_amount),
            },
        )

    CourierShipmentEvent.objects.get_or_create(
        shipment=shipment,
        event_code="shipment_created",
        defaults={
            "status": "pending",
            "description": "Courier shipment created for website order.",
            "payload": {"booking_reference": booking.booking_reference},
            "occurred_at": timezone.now(),
        },
    )
    build_order_timeline(
        order,
        status=order.fulfillment_flow,
        title="Internal courier booking initiated",
        note="Courier booking was created only because this is a website order from our marketplace.",
        actor=actor,
    )
    _ensure_fulfillment_record(
        order,
        {
            "flow": Order.FULFILLMENT_INTERNAL_COURIER,
            "mode": FulfillmentRecord.MODE_BOOK_COURIER,
            "courier_booking_required": True,
        },
    )
    return shipment, booking


@transaction.atomic
def create_courier_shipment_label(shipment, actor=None):
    if shipment.flow_type != Shipment.FLOW_INTERNAL_COURIER or shipment.sync_only:
        raise ValueError("Shipping labels can only be generated for website courier shipments.")
    label_number = f"LBL-{shipment.tracking_number}"
    label_url = f"/courier/labels/{shipment.tracking_number}.pdf"
    label_payload = {
        "tracking_number": shipment.tracking_number,
        "order_number": shipment.order.number,
        "carrier": shipment.carrier,
        "label_number": label_number,
    }
    shipment.label_url = label_url
    shipment.label_payload = label_payload
    shipment.save(update_fields=["label_url", "label_payload", "updated_at"])
    CourierBooking.objects.filter(shipment=shipment).update(label_url=label_url)
    CourierShipmentEvent.objects.create(
        shipment=shipment,
        event_code="label_generated",
        status="label_generated",
        description="Shipping label generated for website courier shipment.",
        payload=label_payload,
    )
    build_order_timeline(
        shipment.order,
        status=shipment.order.fulfillment_flow,
        title="Shipping label generated",
        note="Courier label generated for website courier shipment.",
        actor=actor,
    )
    return {"label_number": label_number, "label_url": label_url, "label_payload": label_payload}


@transaction.atomic
def schedule_courier_pickup(shipment, pickup_date, pickup_slot="", actor=None):
    if shipment.flow_type != Shipment.FLOW_INTERNAL_COURIER or shipment.sync_only:
        raise ValueError("Pickup scheduling is only allowed for website courier shipments.")
    courier_partner = shipment.courier_partner or get_primary_courier_partner(shipment.order.shipping_country_code)
    if courier_partner is None:
        raise ValueError("No courier partner configured.")
    payload = {
        "shipment_tracking_number": shipment.tracking_number,
        "order_number": shipment.order.number,
        "pickup_date": str(pickup_date),
        "pickup_slot": pickup_slot,
    }
    booking = CourierBooking.objects.filter(order=shipment.order, shipment=shipment).first()
    pickup = CourierPickupSchedule.objects.create(
        shipment=shipment,
        courier_partner=courier_partner,
        pickup_date=pickup_date,
        pickup_slot=pickup_slot,
        pickup_reference=f"PU-{uuid4().hex[:12].upper()}",
        status=CourierPickupSchedule.STATUS_CONFIRMED,
        payload=payload,
        response_payload={"status": "scheduled"},
    )
    if booking:
        booking.pickup_reference = pickup.pickup_reference
        booking.pickup_scheduled_at = timezone.now()
        booking.pickup_payload = payload
        booking.save(update_fields=["pickup_reference", "pickup_scheduled_at", "pickup_payload", "updated_at"])
    shipment.pickup_reference = pickup.pickup_reference
    shipment.pickup_scheduled_at = timezone.now()
    shipment.status = "pickup_scheduled"
    shipment.tracking_status = "pickup_scheduled"
    shipment.save(update_fields=["pickup_reference", "pickup_scheduled_at", "status", "tracking_status", "updated_at"])
    CourierShipmentEvent.objects.create(
        shipment=shipment,
        event_code="pickup_scheduled",
        status="pickup_scheduled",
        description="Pickup scheduled for website courier shipment.",
        payload=payload,
    )
    build_order_timeline(
        shipment.order,
        status=shipment.order.fulfillment_flow,
        title="Pickup scheduled",
        note="Courier pickup has been scheduled for website order shipment.",
        actor=actor,
    )
    return pickup


@transaction.atomic
def update_tracking_from_courier(shipment, status, event_code, description="", payload=None, actor=None):
    payload = payload or {}
    shipment.tracking_status = status
    shipment.last_tracking_event_at = timezone.now()
    if status.lower() in {"delivered", "out_for_delivery"}:
        shipment.status = status.lower()
    if status.lower() == "delivered":
        shipment.delivered_at = timezone.now()
    if status.lower() in {"returned", "reverse_completed"}:
        shipment.returned_at = timezone.now()
    shipment.tracking_payload = payload
    shipment.save(
        update_fields=[
            "tracking_status",
            "last_tracking_event_at",
            "status",
            "delivered_at",
            "returned_at",
            "tracking_payload",
            "updated_at",
        ]
    )
    CourierShipmentEvent.objects.create(
        shipment=shipment,
        event_code=event_code,
        status=status,
        description=description,
        payload=payload,
    )
    if status.lower() == "delivered":
        build_order_timeline(
            shipment.order,
            status=Order.STATUS_DELIVERED,
            title="Delivered",
            note="Courier webhook marked the order as delivered.",
            actor=actor,
        )
        send_notification_event(
            event_name="delivery_update",
            context={"order_number": shipment.order.number},
            user=shipment.order.customer
        )
    else:
        send_notification_event(
            event_name="shipment_update",
            context={"order_number": shipment.order.number, "tracking_status": status},
            user=shipment.order.customer
        )

    user_retailer = shipment.order.retailer.account.owner if shipment.order.retailer and getattr(shipment.order.retailer, 'account', None) else None
    send_notification_event(
        event_name="courier_update",
        context={"courier_status": status},
        user=user_retailer
    )

    return shipment


@transaction.atomic
def generate_courier_tracking_snapshot(shipment):
    latest_event = shipment.events.order_by("-occurred_at", "-created_at").first()
    shipment_payload = shipment.tracking_payload or {}
    return {
        "shipment_id": str(shipment.id),
        "tracking_number": shipment.tracking_number,
        "carrier": shipment.carrier,
        "status": shipment.tracking_status or shipment.status,
        "label_url": shipment.label_url,
        "pickup_reference": shipment.pickup_reference,
        "latest_event": {
            "code": latest_event.event_code if latest_event else "",
            "status": latest_event.status if latest_event else "",
            "description": latest_event.description if latest_event else "",
            "occurred_at": latest_event.occurred_at if latest_event else None,
        },
        "payload": shipment_payload,
    }


@transaction.atomic
def process_courier_delivery_webhook(payload, actor=None):
    shipment = None
    shipment_id = payload.get("shipment_id")
    if shipment_id:
        shipment = Shipment.objects.select_related("order", "courier_partner").filter(id=shipment_id).first()
    if shipment is None:
        tracking_number = payload.get("tracking_number") or payload.get("awb_number")
        if not tracking_number:
            raise ValueError("Webhook payload missing tracking reference.")
        shipment = Shipment.objects.select_related("order", "courier_partner").filter(tracking_number=tracking_number).first()
    if shipment is None:
        raise ValueError("Webhook payload missing tracking reference.")
    if shipment is None:
        raise ValueError("Shipment not found.")
    status = payload.get("status", "tracking_update")
    event_code = payload.get("event_code", status)
    description = payload.get("description", "")
    update_tracking_from_courier(shipment, status=status, event_code=event_code, description=description, payload=payload, actor=actor)
    booking = getattr(shipment, "courier_booking", None)
    if booking:
        booking.delivery_webhook_payload = payload
        booking.tracking_payload = payload
        booking.status = CourierBooking.STATUS_BOOKED if status.lower() not in {"cancelled", "failed"} else CourierBooking.STATUS_CANCELLED
        booking.save(
            update_fields=["delivery_webhook_payload", "tracking_payload", "status", "updated_at"]
        )
    return shipment


@transaction.atomic
def initiate_reverse_logistics(order, reason="", actor=None):
    if not order.is_website_order:
        raise ValueError("Reverse logistics courier flow is only allowed for website orders.")
    shipment = order.shipments.filter(flow_type=Order.FULFILLMENT_INTERNAL_COURIER).first()
    if shipment is None:
        raise ValueError("Website order does not have an internal courier shipment.")
    courier_partner = shipment.courier_partner or get_primary_courier_partner(order.shipping_country_code)
    if courier_partner is None:
        raise ValueError("No courier partner configured for reverse logistics.")
    return_pickup = CourierReturnPickup.objects.create(
        order=order,
        shipment=shipment,
        courier_partner=courier_partner,
        pickup_date=timezone.localdate() + timedelta(days=1),
        status=CourierReturnPickup.STATUS_REQUESTED,
        pickup_reference=f"RP-{uuid4().hex[:12].upper()}",
        payload={"reason": reason, "order_number": order.number},
    )
    CourierShipmentEvent.objects.create(
        shipment=shipment,
        event_code="reverse_logistics_requested",
        status="reverse_requested",
        description=reason or "Reverse logistics requested for website order.",
        payload={"return_pickup_id": str(return_pickup.id)},
    )
    build_order_timeline(
        order,
        status=Order.STATUS_PROCESSING,
        title="Reverse logistics requested",
        note=reason or "Reverse logistics initiated for website order.",
        actor=actor,
    )
    return return_pickup


@transaction.atomic
def create_return_pickup(order, reason="", actor=None):
    return initiate_reverse_logistics(order, reason=reason, actor=actor)


@transaction.atomic
def generate_courier_performance_report(courier_partner, period_start, period_end):
    shipments = Shipment.objects.filter(
        courier_partner=courier_partner,
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
    )
    total_shipments = shipments.count()
    delivered_shipments = shipments.filter(Q(status__iexact="delivered") | Q(tracking_status__iexact="delivered")).count()
    cancelled_shipments = shipments.filter(Q(status__iexact="cancelled") | Q(tracking_status__iexact="cancelled")).count()
    return_pickups = CourierReturnPickup.objects.filter(
        courier_partner=courier_partner,
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
    ).count()
    reverse_logistics_count = CourierShipmentEvent.objects.filter(
        shipment__courier_partner=courier_partner,
        event_code="reverse_logistics_requested",
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
    ).count()
    delivery_durations = []
    for shipment in shipments.filter(delivered_at__isnull=False):
        delivery_durations.append((shipment.delivered_at - shipment.created_at).total_seconds() / 3600.0)
    avg_delivery_hours = sum(delivery_durations) / len(delivery_durations) if delivery_durations else 0
    on_time_percentage = Decimal("0.00")
    if total_shipments:
        on_time_percentage = Decimal(delivered_shipments * 100 / total_shipments).quantize(Decimal("0.01"))
    report, _ = CourierPerformanceReport.objects.update_or_create(
        courier_partner=courier_partner,
        period_start=period_start,
        period_end=period_end,
        defaults={
            "total_shipments": total_shipments,
            "delivered_shipments": delivered_shipments,
            "cancelled_shipments": cancelled_shipments,
            "return_pickups": return_pickups,
            "reverse_logistics_count": reverse_logistics_count,
            "avg_delivery_hours": Decimal(str(avg_delivery_hours)).quantize(Decimal("0.01")),
            "on_time_percentage": on_time_percentage,
            "generated_at": timezone.now(),
            "payload": {
                "period_start": str(period_start),
                "period_end": str(period_end),
                "courier_partner": courier_partner.name,
                "total_shipments": total_shipments,
                "delivered_shipments": delivered_shipments,
                "cancelled_shipments": cancelled_shipments,
                "return_pickups": return_pickups,
                "reverse_logistics_count": reverse_logistics_count,
            },
        },
    )
    return report


@transaction.atomic
def build_fulfillment_for_order(order, actor=None):
    rule = resolve_order_fulfillment_rule(order)
    if order.fulfillment_flow != rule["flow"]:
        order.fulfillment_flow = rule["flow"]
        order.shipping_method = rule["flow"]
        order.save(update_fields=["fulfillment_flow", "shipping_method", "updated_at"])

    fulfillment_record = _ensure_fulfillment_record(order, rule)

    if rule["mode"] == FulfillmentRecord.MODE_BOOK_COURIER:
        create_courier_shipment(order, actor=actor)
        return fulfillment_record

    if rule["mode"] == FulfillmentRecord.MODE_SYNC_ONLY:
        Shipment.objects.get_or_create(
            order=order,
            flow_type=rule["flow"],
            defaults={
                "carrier": order.source_channel,
                "booking_source": "external_marketplace",
                "external_shipment_reference": order.external_order_reference,
                "tracking_number": f"EXT-{uuid4().hex[:10].upper()}",
                "status": "synced",
                "tracking_status": "synced",
                "sync_only": True,
                "note": build_sync_only_note(order),
            },
        )
        build_order_timeline(
            order,
            status=order.fulfillment_flow,
            title="External marketplace fulfillment synced",
            note=build_sync_only_note(order),
            actor=actor,
        )
        return fulfillment_record

    build_order_timeline(
        order,
        status=order.fulfillment_flow,
        title="Offline fulfillment registered",
        note="Offline flow does not create courier booking in CommerceOS.",
        actor=actor,
    )
    return fulfillment_record


@transaction.atomic
def build_fulfillment_for_offline_sale(offline_sale, actor=None):
    return FulfillmentRecord.objects.get_or_create(
        offline_sale=offline_sale,
        defaults={
            "source_channel": Order.SOURCE_OFFLINE,
            "flow_type": Order.FULFILLMENT_OFFLINE,
            "mode": FulfillmentRecord.MODE_OFFLINE,
            "status": FulfillmentRecord.STATUS_ACTIVE,
            "courier_booking_required": False,
            "stock_sync_enabled": True,
            "return_sync_enabled": True,
            "refund_sync_enabled": True,
            "settlement_sync_enabled": True,
            "report_sync_enabled": True,
            "note": "Offline sale registered under offline fulfillment flow.",
        },
    )[0]
