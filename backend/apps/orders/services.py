from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.inventory.delivery import estimate_product_delivery, get_request_location_payload
from apps.inventory.services import reserve_stock_for_order
from apps.orders.models import Cart, CartItem, Coupon, Order, OrderItem, OrderTimeline, OrderWorkflowGlobalSetting, OrderWorkflowStoreOverride, OrderWorkflowSetting, DeliveryLabel
from apps.payments.models import Payment
from apps.users.models import UserAddress
from apps.notifications.services import send_notification_event
from apps.users.models import User

TWOPLACES = Decimal("0.01")


def quantize_money(value):
    return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def coupon_feature_enabled():
    from apps.settings_app.models import Setting
    value = Setting.objects.filter(key="coupon_feature", is_active=True).values_list("value", flat=True).first() or {}
    return bool(value.get("enabled", False))


def get_valid_coupon(code, *, now=None):
    if not coupon_feature_enabled() or not code:
        return None
    now = now or timezone.now()
    coupon = Coupon.objects.filter(code=str(code).strip().upper(), is_active=True).first()
    if not coupon or (coupon.starts_at and coupon.starts_at > now) or (coupon.ends_at and coupon.ends_at < now):
        return None
    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        return None
    return coupon


def coupon_discount_for_subtotal(coupon, subtotal):
    if not coupon or subtotal < coupon.minimum_order_amount:
        return Decimal("0.00")
    if coupon.discount_type == Coupon.TYPE_FIXED:
        discount = coupon.discount_value
    else:
        discount = subtotal * coupon.discount_value / Decimal("100")
    if coupon.maximum_discount_amount is not None:
        discount = min(discount, coupon.maximum_discount_amount)
    return quantize_money(min(max(discount, Decimal("0.00")), subtotal))


def apply_coupon_to_cart(cart, code):
    coupon = get_valid_coupon(code)
    if not coupon:
        raise ValueError("This coupon is invalid, expired, or currently unavailable.")
    if coupon.retailer_id and not cart.items.filter(product__retailer_id=coupon.retailer_id).exists():
        raise ValueError("This coupon is not valid for the products in your cart.")
    cart.coupon_code = coupon.code
    cart.save(update_fields=["coupon_code", "updated_at"])
    recalculate_cart(cart)
    if cart.discount_amount <= 0:
        cart.coupon_code = ""
        cart.save(update_fields=["coupon_code", "updated_at"])
        raise ValueError("Your cart does not meet this coupon's minimum order value.")
    return cart


def generate_order_number():
    return f"COS-{timezone.now():%Y%m%d}-{uuid4().hex[:8].upper()}"


def get_or_create_cart(*, user=None, session_key=""):
    if user and getattr(user, "is_authenticated", False):
        cart = (
            Cart.objects.filter(customer=user, status=Cart.STATUS_OPEN, is_active=True)
            .prefetch_related("items__product", "items__variant")
            .first()
        )
        if cart:
            if session_key and not cart.session_key:
                cart.session_key = session_key
                cart.save(update_fields=["session_key", "updated_at"])
            return cart
        return Cart.objects.create(customer=user, session_key=session_key or "")
    if session_key:
        cart = (
            Cart.objects.filter(session_key=session_key, status=Cart.STATUS_OPEN, is_active=True)
            .prefetch_related("items__product", "items__variant")
            .first()
        )
        if cart:
            return cart
    return Cart.objects.create(session_key=session_key or "")


def ensure_request_cart(request):
    if not request.session.session_key:
        request.session.create()
    cart = get_or_create_cart(
        user=request.user,
        session_key=request.session.session_key,
    )
    sync_session_cart_to_db(request, cart=cart)
    recalculate_cart(cart)
    return cart


def sync_session_cart_to_db(request, cart=None):
    cart = cart or ensure_request_cart(request)
    session_cart = request.session.get("cart", {})
    for cart_key, payload in session_cart.items():
        from apps.catalog.models import Product

        product_id = str(cart_key).split(":", 1)[0]
        product = Product.objects.filter(id=product_id, is_active=True).first()
        if not product:
            continue
        unit_price = quantize_money(payload.get("unit_price", product.discount_price or product.price or 0))
        variant_id = payload.get("variant_id")
        variant = None
        if variant_id:
            from apps.catalog.models import ProductVariant
            variant = ProductVariant.objects.filter(product=product, id=variant_id).first()

        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            variant=variant,
            defaults={
                "quantity": int(payload.get("quantity", 1)),
                "unit_price": variant.price if variant else product.price,
                "discount_price": unit_price,
                "tax_rate": getattr(variant, "tax_rate", None) or product.tax_rate,
            },
        )
        if not created:
            item.quantity = max(item.quantity, int(payload.get("quantity", 1)))
            item.discount_price = unit_price
            item.unit_price = variant.price if variant else product.price
            item.tax_rate = getattr(variant, "tax_rate", None) or product.tax_rate
            item.save(
                update_fields=[
                    "quantity",
                    "discount_price",
                    "unit_price",
                    "tax_rate",
                    "updated_at",
                ]
            )
    return cart


def cart_delivery_payload(request, cart):
    payload = get_request_location_payload(request)
    if payload.get("pincode") and cart.delivery_postal_code != payload["pincode"]:
        cart.delivery_postal_code = payload["pincode"]
        cart.save(update_fields=["delivery_postal_code", "updated_at"])
    return payload


def recalculate_cart(cart, location_payload=None):
    subtotal = Decimal("0.00")
    tax_amount = Decimal("0.00")
    shipping_amount = Decimal("0.00")
    items = list(
        cart.items.select_related("product", "variant", "product__store", "product__retailer", "product__category")
    )
    group_subtotals = {}
    for item in items:
        price_source = item.variant if item.variant else item.product
        price = price_source.discount_price or price_source.price or Decimal("0.00")
        base_price = price_source.price or price
        item.unit_price = quantize_money(base_price)
        item.discount_price = quantize_money(price)
        item.tax_rate = getattr(item.variant, "tax_rate", None) or item.product.tax_rate
        item.line_subtotal = quantize_money(item.discount_price * item.quantity)
        item.line_tax = quantize_money(item.line_subtotal * (item.tax_rate / Decimal("100")))
        estimate = estimate_product_delivery(item.product, location_payload=location_payload or {})
        if estimate.get("estimated_date"):
            item.delivery_estimate_date = estimate["estimated_date"]
        group_subtotals.setdefault(item.product.retailer_id, Decimal("0.00"))
        group_subtotals[item.product.retailer_id] += item.line_subtotal
        item.shipping_amount = Decimal("0.00")
        item.save(
            update_fields=[
                "unit_price",
                "discount_price",
                "tax_rate",
                "line_subtotal",
                "line_tax",
                "updated_at",
            ]
        )
    assigned_shipping_groups = set()
    for item in items:
        retailer_id = item.product.retailer_id
        group_shipping = Decimal("0.00") if group_subtotals[retailer_id] >= Decimal("100.00") else Decimal("12.00")
        if retailer_id not in assigned_shipping_groups:
            item.shipping_amount = quantize_money(group_shipping)
            assigned_shipping_groups.add(retailer_id)
        else:
            item.shipping_amount = Decimal("0.00")
        item.line_total = quantize_money(item.line_subtotal + item.line_tax + item.shipping_amount)
        item.save(update_fields=["line_total", "updated_at"])
        subtotal += item.line_subtotal
        tax_amount += item.line_tax
        shipping_amount += item.shipping_amount
    cart.subtotal_amount = quantize_money(subtotal)
    coupon = get_valid_coupon(cart.coupon_code)
    eligible_subtotal = subtotal
    if coupon and coupon.retailer_id:
        eligible_subtotal = sum(
            item.line_subtotal for item in items if item.product.retailer_id == coupon.retailer_id
        )
    cart.discount_amount = coupon_discount_for_subtotal(coupon, quantize_money(eligible_subtotal))
    cart.tax_amount = quantize_money(tax_amount)
    cart.shipping_amount = quantize_money(shipping_amount)
    cart.total_amount = quantize_money(
        cart.subtotal_amount - cart.discount_amount + cart.tax_amount + cart.shipping_amount
    )
    cart.save(
        update_fields=[
            "subtotal_amount",
            "discount_amount",
            "tax_amount",
            "shipping_amount",
            "total_amount",
            "updated_at",
        ]
    )
    return cart


def get_available_cart_quantity(*, product, variant=None):
    if variant is not None:
        return variant.available_qty
    return product.available_qty


def validate_cart_stock(*, product, variant=None, requested_quantity):
    available = get_available_cart_quantity(product=product, variant=variant)
    if requested_quantity > available:
        label = variant.name if variant else product.name
        raise ValueError(f"Only {available} in stock for {label}.")
    return available


def add_product_to_cart(*, cart, product, quantity=1, variant=None):
    current_quantity = 0
    existing_item = CartItem.objects.filter(cart=cart, product=product, variant=variant).first()
    if existing_item:
        current_quantity = existing_item.quantity
    validate_cart_stock(product=product, variant=variant, requested_quantity=current_quantity + quantity)
    item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        variant=variant,
        defaults={
            "quantity": quantity,
            "unit_price": product.price,
            "discount_price": product.discount_price or product.price,
            "tax_rate": getattr(variant, "tax_rate", None) or product.tax_rate,
        },
    )
    if not created:
        item.quantity += quantity
        item.save(update_fields=["quantity", "updated_at"])
    recalculate_cart(cart)
    return item


def update_cart_item_quantity(*, cart_item, quantity):
    if quantity <= 0:
        cart_item.delete()
        recalculate_cart(cart_item.cart)
        return None
    validate_cart_stock(product=cart_item.product, variant=cart_item.variant, requested_quantity=quantity)
    cart_item.quantity = quantity
    cart_item.save(update_fields=["quantity", "updated_at"])
    recalculate_cart(cart_item.cart)
    return cart_item


def build_order_timeline(order, status, title, note="", actor=None):
    return OrderTimeline.objects.create(
        order=order,
        status=status,
        title=title,
        note=note,
        actor=actor,
    )


def get_order_workflow_setting(retailer=None, store=None):
    """Return a store override when enabled, otherwise the global default."""
    if store is not None:
        override = OrderWorkflowStoreOverride.objects.filter(store=store, is_active=True).first()
        if override:
            return override
    setting, _ = OrderWorkflowGlobalSetting.objects.get_or_create(key="default")
    return setting


def get_order_workflow_setting_for_order(order):
    item = order.items.select_related("product__store").first()
    return get_order_workflow_setting(order.retailer, getattr(getattr(item, "product", None), "store", None))


def order_stakeholder_emails(order):
    emails = set(User.objects.filter(is_active=True, is_superuser=True).exclude(email="").values_list("email", flat=True))
    owner = getattr(getattr(order.retailer, "account", None), "owner", None)
    if owner and owner.email:
        emails.add(owner.email)
    return list(emails)


@transaction.atomic
def generate_delivery_label(order, actor=None):
    shipment = order.shipments.select_related("courier_partner").first()
    invoice = order.invoices.order_by("-created_at").first()
    retailer = order.retailer
    tracking_number = shipment.tracking_number if shipment else f"NBX-{order.number}"
    carrier = shipment.carrier if shipment and shipment.carrier else "Nuboxed Logistics"
    service_level = "EXPRESS" if str(order.shipping_method).lower() in {"express", "next_day", "priority"} else "STANDARD"
    destination_hub = (order.shipping_city or order.shipping_country_code or "HUB").upper().replace(" ", "-")[:10]
    origin = (retailer.display_name or retailer.legal_name or "NUBOXED").upper()[:3]
    address = ", ".join(filter(None, [order.shipping_address_line1, order.shipping_address_line2, order.shipping_city, order.shipping_state, order.shipping_postal_code, order.shipping_country_code]))
    payload = {
        "order_number": order.number, "customer": order.shipping_full_name or order.customer.get_full_name() or order.customer.email,
        "phone": order.shipping_phone, "address": address,
        "items": [{"name": item.product.name, "variant": item.variant.name if item.variant else "", "sku": item.variant.sku if item.variant else item.product.sku, "quantity": item.quantity, "imei_numbers": item.imei_numbers or []} for item in order.items.select_related("product", "variant")],
        "carrier": carrier, "service_level": service_level, "route_origin": origin,
        "destination_hub": destination_hub, "zone": order.shipping_country_code or "INTL",
        "sort_code": f"{destination_hub[:3]}-{str(order.number)[-3:]}", "tracking_number": tracking_number,
        "tracking_url": f"/account/orders/{order.pk}/track/",
        "invoice_number": invoice.invoice_number if invoice else f"INV-{order.number}",
        "order_date": (order.placed_at or order.created_at).strftime("%d %b %Y"),
        "payment_label": "PREPAID" if order.payment_status in {"paid", "authorized"} else "COD / PAY ON DELIVERY",
        "declared_value": str(order.total_amount), "currency": order.currency_code, "package_count": "1 of 1",
        "units": sum(item.quantity for item in order.items.all()), "return_address": retailer.business_address or retailer.display_name or retailer.legal_name,
        "return_name": retailer.display_name or retailer.legal_name, "return_tax_id": retailer.vat_number or "Not specified",
        "support_phone": retailer.support_phone or "Not specified", "weight": "Not declared", "dimensions": "Not declared",
        "handling": "Standard handling", "reference": f"NBX-{str(order.number).replace('ORD-', '')}-{origin}",
    }
    label, _ = DeliveryLabel.objects.update_or_create(order=order, defaults={"label_number": f"LBL-{order.number}", "payload": payload, "generated_by": actor, "status": DeliveryLabel.STATUS_GENERATED, "printed_at": None})
    return label


@transaction.atomic
def update_order_status(order, status, actor=None, note=""):
    valid = {key for key, _ in Order.STATUS_CHOICES}
    if status not in valid:
        raise ValueError("Invalid order status.")
    if order.status == status:
        return order
    order.status = status
    order._timeline_actor = actor
    order._timeline_note = note
    updates = ["status", "updated_at"]
    if status == Order.STATUS_CONFIRMED and not order.confirmed_at:
        order.confirmed_at = timezone.now(); updates.append("confirmed_at")
    if status == Order.STATUS_CANCELLED:
        order.cancelled_at = timezone.now(); updates.append("cancelled_at")
    order.save(update_fields=updates)
    fulfillment_warning = ""
    if status == Order.STATUS_CONFIRMED:
        from apps.shipments.services import build_fulfillment_for_order
        try:
            build_fulfillment_for_order(order, actor=actor)
        except ValueError as exc:
            # The order status must remain usable even when operations has not
            # configured a courier partner yet. Keep the fulfillment issue in
            # the order timeline for admin/retailer follow-up.
            fulfillment_warning = str(exc)
            build_order_timeline(
                order,
                status=status,
                title="Courier booking pending",
                note=fulfillment_warning,
                actor=actor,
            )
    config = get_order_workflow_setting_for_order(order)
    if config.notify_customer_status_changed:
        send_notification_event("order_status_changed", {"order_number": order.number, "status": order.get_status_display(), "amount": str(order.total_amount)}, user=order.customer, extra_recipients=order_stakeholder_emails(order))
    order._fulfillment_warning = fulfillment_warning
    return order


def apply_order_automation(order, actor=None):
    config = get_order_workflow_setting_for_order(order)
    if config.auto_invoice:
        from apps.payments.services import generate_invoice_for_order
        generate_invoice_for_order(order, actor=actor)
    if config.auto_label:
        generate_delivery_label(order, actor=actor)
    return order


def copy_address_to_order(order, address):
    order.address = address
    order.shipping_full_name = address.full_name or order.customer.get_full_name() or order.customer.username
    order.shipping_phone = address.phone or order.customer.phone
    order.shipping_address_line1 = address.address_line1
    order.shipping_address_line2 = address.address_line2
    order.shipping_city = address.city
    order.shipping_state = address.state
    order.shipping_postal_code = address.postal_code
    order.shipping_country_code = address.country_code


@transaction.atomic
def _create_order_for_items(*, request, cart, address, payment_method, note="", cart_items):
    first_item = cart_items[0]
    subtotal_amount = quantize_money(sum(item.line_subtotal for item in cart_items))
    tax_amount = quantize_money(sum(item.line_tax for item in cart_items))
    shipping_amount = quantize_money(sum(item.shipping_amount for item in cart_items))
    coupon = get_valid_coupon(cart.coupon_code)
    eligible_subtotal = subtotal_amount if not coupon or not coupon.retailer_id else quantize_money(
        sum(item.line_subtotal for item in cart_items if item.product.retailer_id == coupon.retailer_id)
    )
    discount_amount = coupon_discount_for_subtotal(coupon, eligible_subtotal)
    total_amount = quantize_money(subtotal_amount - discount_amount + tax_amount + shipping_amount)
    order = Order.objects.create(
        customer=request.user,
        retailer=first_item.product.retailer,
        cart=cart,
        number=generate_order_number(),
        status=Order.STATUS_PENDING,
        placed_at=timezone.now(),
        payment_method=payment_method,
        coupon_code=cart.coupon_code,
        subtotal_amount=subtotal_amount,
        discount_amount=discount_amount,
        tax_amount=tax_amount,
        shipping_amount=shipping_amount,
        total_amount=total_amount,
        note=note,
    )
    copy_address_to_order(order, address)
    order.save()

    item_estimates = []
    delivery_payload = cart_delivery_payload(request, cart)
    for cart_item in cart_items:
        estimate = estimate_product_delivery(cart_item.product, location_payload=delivery_payload)
        item_estimates.append(estimate.get("estimated_date"))
        OrderItem.objects.create(
            order=order,
            product=cart_item.product,
            variant=cart_item.variant,
            warehouse=estimate.get("warehouse"),
            quantity=cart_item.quantity,
            unit_price=cart_item.unit_price,
            discount_price=cart_item.discount_price,
            tax_rate=cart_item.tax_rate,
            tax_amount=cart_item.line_tax,
            shipping_amount=cart_item.shipping_amount,
            delivery_estimate_date=estimate.get("estimated_date"),
            line_total=cart_item.line_total,
        )

    order.delivery_estimate_date = max([date for date in item_estimates if date], default=None)
    order.save(update_fields=["delivery_estimate_date", "updated_at"])

    if coupon and discount_amount:
        Coupon.objects.filter(pk=coupon.pk).update(used_count=F("used_count") + 1)

    reserve_stock_for_order(order)
    build_order_timeline(
        order,
        status=Order.STATUS_PENDING,
        title="Order placed",
        note="Stock reserved during checkout. Waiting for confirmation.",
        actor=request.user,
    )
    Payment.objects.create(
        order=order,
        provider=payment_method,
        external_reference=f"PAY-{uuid4().hex[:12].upper()}",
        amount=order.total_amount,
        status=Payment._meta.get_field("status").default,
    )
    
    workflow = get_order_workflow_setting_for_order(order)
    if workflow.notify_customer_order_placed:
        send_notification_event(event_name="new_order", context={"order_number": order.number, "amount": str(order.total_amount)}, user=order.customer, extra_recipients=order_stakeholder_emails(order))
    apply_order_automation(order, actor=request.user)
    
    return order


@transaction.atomic
def create_orders_from_cart(*, request, cart, address, payment_method, note=""):
    if not cart.items.exists():
        raise ValueError("Cart is empty.")
    if address is None:
        raise ValueError("Shipping address is required.")
    if not getattr(request.user, "is_authenticated", False):
        raise ValueError("Login required to place order.")

    delivery_payload = cart_delivery_payload(request, cart)
    recalculate_cart(cart, location_payload=delivery_payload)
    grouped_items = {}
    for cart_item in cart.items.select_related("product", "variant", "product__retailer"):
        grouped_items.setdefault(cart_item.product.retailer_id, []).append(cart_item)

    orders = []
    for cart_items in grouped_items.values():
        order = _create_order_for_items(
            request=request,
            cart=cart,
            address=address,
            payment_method=payment_method,
            note=note,
            cart_items=cart_items,
        )
        orders.append(order)
    cart.status = Cart.STATUS_CONVERTED
    cart.save(update_fields=["status", "updated_at"])
    return orders


@transaction.atomic
def confirm_website_order(order, actor=None):
    if order.status != Order.STATUS_PENDING:
        return order
    order.status = Order.STATUS_CONFIRMED
    order.payment_status = Order.PAYMENT_PENDING
    order.confirmed_at = timezone.now()
    order.save(update_fields=["status", "payment_status", "confirmed_at", "updated_at"])
    build_order_timeline(
        order,
        status=Order.STATUS_CONFIRMED,
        title="Order confirmed",
        note="Internal courier fulfillment started.",
        actor=actor,
    )
    from apps.shipments.services import build_fulfillment_for_order

    try:
        build_fulfillment_for_order(order, actor=actor)
    except ValueError as exc:
        build_order_timeline(order, status=Order.STATUS_CONFIRMED, title="Courier booking pending", note=str(exc), actor=actor)
    return order


@transaction.atomic
def confirm_order(order, actor=None):
    if order.status != Order.STATUS_PENDING:
        return order
    order.status = Order.STATUS_CONFIRMED
    order.payment_status = Order.PAYMENT_PENDING
    order.confirmed_at = timezone.now()
    order.save(update_fields=["status", "payment_status", "confirmed_at", "updated_at"])
    build_order_timeline(
        order,
        status=Order.STATUS_CONFIRMED,
        title="Order confirmed",
        note=f"{order.get_source_channel_display()} order confirmed.",
        actor=actor,
    )
    from apps.shipments.services import build_fulfillment_for_order

    try:
        build_fulfillment_for_order(order, actor=actor)
    except ValueError as exc:
        build_order_timeline(order, status=Order.STATUS_CONFIRMED, title="Courier booking pending", note=str(exc), actor=actor)
    return order


def resolve_checkout_address(user, address_id=None):
    queryset = UserAddress.objects.filter(user=user, is_active=True)
    if address_id:
        return queryset.filter(id=address_id).first()
    return queryset.filter(is_default=True).first() or queryset.first()


@transaction.atomic
def create_external_marketplace_order(
    *,
    retailer,
    source_channel,
    external_order_reference,
    connector=None,
    currency_code="EUR",
    customer,
    shipping_payload=None,
    total_amount=Decimal("0.00"),
    note="",
):
    if customer is None:
        raise ValueError("External marketplace order import currently requires a mapped local customer.")
    shipping_payload = shipping_payload or {}
    order = Order.objects.create(
        customer=customer,
        retailer=retailer,
        number=generate_order_number(),
        status=Order.STATUS_PENDING,
        source_channel=source_channel,
        marketplace_connector=connector,
        external_order_reference=external_order_reference,
        fulfillment_flow={
            Order.SOURCE_AMAZON: Order.FULFILLMENT_AMAZON,
            Order.SOURCE_FLIPKART: Order.FULFILLMENT_FLIPKART,
            Order.SOURCE_EBAY: Order.FULFILLMENT_EBAY,
            Order.SOURCE_SHOPIFY: Order.FULFILLMENT_PLATFORM,
            Order.SOURCE_WOOCOMMERCE: Order.FULFILLMENT_PLATFORM,
        }.get(source_channel, Order.FULFILLMENT_PLATFORM),
        currency_code=currency_code,
        shipping_full_name=shipping_payload.get("full_name", ""),
        shipping_phone=shipping_payload.get("phone", ""),
        shipping_address_line1=shipping_payload.get("address_line1", ""),
        shipping_address_line2=shipping_payload.get("address_line2", ""),
        shipping_city=shipping_payload.get("city", ""),
        shipping_state=shipping_payload.get("state", ""),
        shipping_postal_code=shipping_payload.get("postal_code", ""),
        shipping_country_code=shipping_payload.get("country_code", "DE"),
        total_amount=quantize_money(total_amount),
        placed_at=timezone.now(),
        note=note,
    )
    build_order_timeline(
        order,
        status=Order.STATUS_PENDING,
        title="External marketplace order synced",
        note="Order synced into CommerceOS. Internal courier booking is disabled for external marketplace flow.",
    )
    return order
