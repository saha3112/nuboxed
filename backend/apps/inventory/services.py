from decimal import Decimal

from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from django.utils.text import slugify

from apps.catalog.models import ProductVariant
from apps.inventory.models import (
    LowStockAlert,
    OfflineSale,
    StockAdjustment,
    StockItem,
    StockLedger,
    StockReservation,
    Warehouse,
)


def canonical_stock_items(queryset=None):
    """Return stock rows that represent the product's sellable stock model.

    Variant products use variant-level stock.  A legacy/general row is kept in
    the database for audit and reconciliation, but must not be displayed as
    sellable stock alongside variant rows.  Products without variants use the
    general row instead.
    """
    queryset = queryset if queryset is not None else StockItem.objects.all()
    has_variants = ProductVariant.objects.filter(product_id=OuterRef("product_id"))
    return queryset.annotate(_product_has_variants=Exists(has_variants)).filter(
        Q(_product_has_variants=True, variant_id__isnull=False)
        | Q(_product_has_variants=False, variant_id__isnull=True)
    )


def ensure_default_warehouse(*, retailer, store=None):
    warehouse = Warehouse.objects.filter(retailer=retailer, is_default=True).order_by("-created_at").first()
    if warehouse:
        return warehouse

    if store is not None:
        warehouse = Warehouse.objects.filter(retailer=retailer, store=store).order_by("-is_default", "name").first()
        if warehouse:
            return warehouse

    warehouse = Warehouse.objects.filter(retailer=retailer).order_by("-is_default", "name").first()
    if warehouse:
        return warehouse

    base_name = f"{(store.name if store else '') or retailer.display_name or retailer.legal_name} Default Warehouse".strip()
    base_code_source = f"{(store.slug if store else '') or retailer.legal_name or 'warehouse'}-default"
    base_code = slugify(base_code_source).replace("-", "").upper()[:18] or "WHDEFAULT"
    code = base_code
    counter = 1
    while Warehouse.objects.filter(code=code).exists():
        code = f"{base_code}{counter}"
        counter += 1

    return Warehouse.objects.create(
        retailer=retailer,
        store=store,
        name=base_name,
        code=code,
        delivery_days=getattr(store, "average_delivery_days", 3) if store else 3,
        handling_time_days=1,
        is_default=True,
    )


def _get_stock_item(*, warehouse, product, variant=None):
    return StockItem.objects.get_or_create(
        warehouse=warehouse,
        product=product,
        variant=variant,
        defaults={"low_stock_threshold": 0},
    )[0]


def _log_stock_movement(*, stock_item, movement_type, quantity_delta, reference_type="", reference_id="", note="", actor=None):
    return StockLedger.objects.create(
        warehouse=stock_item.warehouse,
        stock_item=stock_item,
        product=stock_item.product,
        variant=stock_item.variant,
        movement_type=movement_type,
        quantity_delta=quantity_delta,
        reference_type=reference_type,
        reference_id=str(reference_id) if reference_id else "",
        note=note,
        created_by=actor,
    )


def _refresh_low_stock_alert(stock_item):
    if stock_item.is_low_stock:
        alert, created = LowStockAlert.objects.get_or_create(
            stock_item=stock_item,
            resolved_at__isnull=True,
            defaults={"triggered_quantity": stock_item.available_quantity},
        )
        if created:
            from apps.notifications.services import send_notification_event
            user = stock_item.product.retailer.account.owner if stock_item.product.retailer and getattr(stock_item.product.retailer, 'account', None) else None
            send_notification_event(
                event_name="stock_low",
                context={"sku": stock_item.product.sku, "quantity": str(stock_item.available_quantity)},
                user=user
            )
    else:
        LowStockAlert.objects.filter(stock_item=stock_item, resolved_at__isnull=True).update(
            resolved_at=timezone.now()
        )


@transaction.atomic
def sync_product_stock(*, product, available_quantity, variant=None, warehouse=None):
    warehouse = warehouse or ensure_default_warehouse(retailer=product.retailer, store=product.store)
    stock_item, _ = StockItem.objects.get_or_create(
        warehouse=warehouse,
        product=product,
        variant=variant,
        defaults={"low_stock_threshold": 0},
    )
    available_quantity = max(int(available_quantity or 0), 0)
    stock_item.on_hand_quantity = available_quantity + max(stock_item.reserved_quantity, 0)
    if stock_item.reserved_quantity > stock_item.on_hand_quantity:
        stock_item.reserved_quantity = stock_item.on_hand_quantity
    stock_item.save(update_fields=["on_hand_quantity", "reserved_quantity", "updated_at"])
    _refresh_low_stock_alert(stock_item)
    return stock_item


@transaction.atomic
def manual_stock_adjustment(*, warehouse, product, variant=None, quantity, adjustment_type, note="", actor=None):
    stock_item = _get_stock_item(warehouse=warehouse, product=product, variant=variant)
    delta = quantity if adjustment_type == StockAdjustment.TYPE_INCREASE else -quantity
    stock_item.on_hand_quantity += delta
    if adjustment_type == StockAdjustment.TYPE_DAMAGE:
        stock_item.damaged_quantity += quantity
    stock_item.save()

    adjustment = StockAdjustment.objects.create(
        warehouse=warehouse,
        product=product,
        variant=variant,
        quantity=quantity,
        adjustment_type=adjustment_type,
        note=note,
        created_by=actor,
    )
    ledger_type = (
        StockLedger.TYPE_DAMAGE
        if adjustment_type == StockAdjustment.TYPE_DAMAGE
        else StockLedger.TYPE_MANUAL_ADJUSTMENT
    )
    _log_stock_movement(
        stock_item=stock_item,
        movement_type=ledger_type,
        quantity_delta=delta,
        reference_type="stock_adjustment",
        reference_id=adjustment.id,
        note=note,
        actor=actor,
    )
    _refresh_low_stock_alert(stock_item)
    return adjustment


@transaction.atomic
def reserve_stock_for_order(order):
    reservations = []
    for item in order.items.select_related("product", "variant", "warehouse"):
        warehouse = item.warehouse or Warehouse.objects.filter(retailer=order.retailer, is_default=True).first()
        if warehouse is None:
            raise ValueError("No warehouse available for stock reservation.")
        stock_item = _get_stock_item(
            warehouse=warehouse,
            product=item.product,
            variant=item.variant,
        )
        if stock_item.available_quantity < item.quantity:
            raise ValueError(f"Insufficient stock for {item.product.name}.")
        stock_item.reserved_quantity += item.quantity
        stock_item.save()
        reservation = StockReservation.objects.create(
            warehouse=warehouse,
            stock_item=stock_item,
            product=item.product,
            variant=item.variant,
            order=order,
            order_item=item,
            quantity=item.quantity,
            status=StockReservation.STATUS_RESERVED,
        )
        _log_stock_movement(
            stock_item=stock_item,
            movement_type=StockLedger.TYPE_RESERVATION,
            quantity_delta=-item.quantity,
            reference_type="order",
            reference_id=order.id,
            note=f"Reserved for order {order.number}",
        )
        _refresh_low_stock_alert(stock_item)
        reservations.append(reservation)
    return reservations


@transaction.atomic
def reserve_stock_for_order_item(order_item):
    order = order_item.order
    warehouse = order_item.warehouse or Warehouse.objects.filter(retailer=order.retailer, is_default=True).first()
    if warehouse is None:
        raise ValueError("No warehouse available for stock reservation.")
    stock_item = _get_stock_item(
        warehouse=warehouse,
        product=order_item.product,
        variant=order_item.variant,
    )
    if stock_item.available_quantity < order_item.quantity:
        raise ValueError(f"Insufficient stock for {order_item.product.name}.")
    stock_item.reserved_quantity += order_item.quantity
    stock_item.save()
    reservation = StockReservation.objects.create(
        warehouse=warehouse,
        stock_item=stock_item,
        product=order_item.product,
        variant=order_item.variant,
        order=order,
        order_item=order_item,
        quantity=order_item.quantity,
        status=StockReservation.STATUS_RESERVED,
    )
    _log_stock_movement(
        stock_item=stock_item,
        movement_type=StockLedger.TYPE_RESERVATION,
        quantity_delta=-order_item.quantity,
        reference_type="order",
        reference_id=order.id,
        note=f"Reserved for order {order.number}",
    )
    _refresh_low_stock_alert(stock_item)
    return reservation


@transaction.atomic
def consume_reserved_stock_for_order(order):
    for reservation in order.stock_reservations.filter(status=StockReservation.STATUS_RESERVED).select_related("stock_item"):
        stock_item = reservation.stock_item
        stock_item.reserved_quantity -= reservation.quantity
        stock_item.on_hand_quantity -= reservation.quantity
        stock_item.save()
        reservation.status = StockReservation.STATUS_CONSUMED
        reservation.save(update_fields=["status", "updated_at"])
        _log_stock_movement(
            stock_item=stock_item,
            movement_type=StockLedger.TYPE_ONLINE_SALE,
            quantity_delta=-reservation.quantity,
            reference_type="order",
            reference_id=order.id,
            note=f"Consumed for order {order.number}",
        )
        _refresh_low_stock_alert(stock_item)
    order.stock_deducted_at = timezone.now()
    order.save(update_fields=["stock_deducted_at", "updated_at"])
    return order


@transaction.atomic
def consume_reserved_stock_for_order_item(order_item):
    reservation = order_item.stock_reservations.filter(status=StockReservation.STATUS_RESERVED).select_related("stock_item").first()
    if reservation is None:
        return order_item
    stock_item = reservation.stock_item
    stock_item.reserved_quantity -= reservation.quantity
    stock_item.on_hand_quantity -= reservation.quantity
    stock_item.save()
    reservation.status = StockReservation.STATUS_CONSUMED
    reservation.save(update_fields=["status", "updated_at"])
    _log_stock_movement(
        stock_item=stock_item,
        movement_type=StockLedger.TYPE_ONLINE_SALE,
        quantity_delta=-reservation.quantity,
        reference_type="order",
        reference_id=order_item.order.id,
        note=f"Consumed for order {order_item.order.number}",
    )
    _refresh_low_stock_alert(stock_item)
    return order_item


@transaction.atomic
def restore_stock_for_cancelled_order(order):
    reservations = order.stock_reservations.select_related("stock_item")
    for reservation in reservations:
        stock_item = reservation.stock_item
        if reservation.status == StockReservation.STATUS_RESERVED:
            stock_item.reserved_quantity -= reservation.quantity
            stock_item.save()
            reservation.status = StockReservation.STATUS_RELEASED
            movement_type = StockLedger.TYPE_RESERVATION_RELEASE
        elif reservation.status == StockReservation.STATUS_CONSUMED:
            stock_item.on_hand_quantity += reservation.quantity
            stock_item.save()
            reservation.status = StockReservation.STATUS_RESTORED
            movement_type = StockLedger.TYPE_CANCEL_RESTORE
        else:
            continue
        reservation.save(update_fields=["status", "updated_at"])
        _log_stock_movement(
            stock_item=stock_item,
            movement_type=movement_type,
            quantity_delta=reservation.quantity,
            reference_type="order",
            reference_id=order.id,
            note=f"Restored for cancelled order {order.number}",
        )
        _refresh_low_stock_alert(stock_item)
    order.stock_restored_at = timezone.now()
    order.save(update_fields=["stock_restored_at", "updated_at"])
    return order


@transaction.atomic
def create_offline_sale(*, warehouse, store, product, variant=None, quantity, unit_price=Decimal("0"), sold_at=None, note="", actor=None):
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")
    if product.variants.exists() and variant is None:
        raise ValueError("Select the exact product variant for this sale.")
    if variant is not None and variant.product_id != product.id:
        raise ValueError("The selected variant does not belong to this product.")
    if product.store_id and product.store_id != store.id:
        raise ValueError("The selected store does not match the product store.")
    if warehouse.retailer_id != product.retailer_id:
        raise ValueError("The selected warehouse does not belong to this retailer.")
    if warehouse.store_id and warehouse.store_id != store.id:
        raise ValueError("The selected warehouse belongs to a different store.")

    # Consume the existing backend stock row only. Do not create a new stock
    # row during a sale, otherwise an invalid/missing mapping could look like
    # stock was available when it was not.
    stock_item = (
        StockItem.objects.select_for_update()
        .filter(warehouse=warehouse, product=product, variant=variant)
        .first()
    )
    if stock_item is None:
        raise ValueError("No stock record exists for this product, variant, and warehouse.")
    if stock_item.available_quantity < quantity:
        raise ValueError("Insufficient stock for offline sale.")
    stock_item.on_hand_quantity -= quantity
    stock_item.save()
    sale = OfflineSale.objects.create(
        warehouse=warehouse,
        store=store,
        product=product,
        variant=variant,
        quantity=quantity,
        unit_price=unit_price,
        total_amount=unit_price * quantity,
        sold_at=sold_at or timezone.now(),
        note=note,
        created_by=actor,
    )
    _log_stock_movement(
        stock_item=stock_item,
        movement_type=StockLedger.TYPE_OFFLINE_SALE,
        quantity_delta=-quantity,
        reference_type="offline_sale",
        reference_id=sale.id,
        note=note,
        actor=actor,
    )
    _refresh_low_stock_alert(stock_item)
    from apps.shipments.services import build_fulfillment_for_offline_sale
    
    from apps.notifications.services import send_notification_event
    user_retailer = store.retailer.account.owner if store.retailer and getattr(store.retailer, 'account', None) else None
    send_notification_event(
        event_name="offline_sale",
        context={"amount": str(sale.total_amount)},
        user=user_retailer
    )

    build_fulfillment_for_offline_sale(sale, actor=actor)
    return sale


@transaction.atomic
def mark_return_pending_qc(return_request):
    if hasattr(return_request, "order_item") and return_request.order_item:
        item = return_request.order_item
        if item is not None and item.warehouse is not None:
            stock_item = _get_stock_item(warehouse=item.warehouse, product=item.product, variant=item.variant)
            stock_item.returned_quantity += getattr(return_request, "quantity", 1)
            stock_item.save()
            _log_stock_movement(
                stock_item=stock_item,
                movement_type=StockLedger.TYPE_RETURN_PENDING,
                quantity_delta=0,
                reference_type="return_request",
                reference_id=return_request.id,
                note="Return received, pending QC",
            )
    elif hasattr(return_request, "items") and return_request.items.exists():
        for item in return_request.items.all():
            order_item = item.order_item
            if order_item is not None and order_item.warehouse is not None:
                stock_item = _get_stock_item(warehouse=order_item.warehouse, product=order_item.product, variant=order_item.variant)
                stock_item.returned_quantity += item.quantity
                stock_item.save()
                _log_stock_movement(
                    stock_item=stock_item,
                    movement_type=StockLedger.TYPE_RETURN_PENDING,
                    quantity_delta=0,
                    reference_type="return_request",
                    reference_id=return_request.id,
                    note=f"Return item {order_item.product.name} received, pending QC",
                )
    return return_request


@transaction.atomic
def restock_return_after_qc(return_request, actor=None):
    if hasattr(return_request, "order_item") and return_request.order_item:
        item = return_request.order_item
        if item is None or item.warehouse is None:
            raise ValueError("Return request must reference a stocked order item.")
        stock_item = _get_stock_item(warehouse=item.warehouse, product=item.product, variant=item.variant)
        qty = getattr(return_request, "quantity", 1)
        stock_item.returned_quantity = max(0, stock_item.returned_quantity - qty)
        stock_item.on_hand_quantity += qty
        stock_item.save()
        _log_stock_movement(
            stock_item=stock_item,
            movement_type=StockLedger.TYPE_RETURN_RESTOCK,
            quantity_delta=qty,
            reference_type="return_request",
            reference_id=return_request.id,
            note="Returned stock restored after QC approval",
            actor=actor,
        )
        _refresh_low_stock_alert(stock_item)
    elif hasattr(return_request, "items") and return_request.items.exists():
        for item in return_request.items.all():
            order_item = item.order_item
            if order_item is None or order_item.warehouse is None:
                continue
            stock_item = _get_stock_item(warehouse=order_item.warehouse, product=order_item.product, variant=order_item.variant)
            stock_item.returned_quantity = max(0, stock_item.returned_quantity - item.quantity)
            if item.qc_status == "passed":
                stock_item.on_hand_quantity += item.quantity
                stock_item.save()
                _log_stock_movement(
                    stock_item=stock_item,
                    movement_type=StockLedger.TYPE_RETURN_RESTOCK,
                    quantity_delta=item.quantity,
                    reference_type="return_request",
                    reference_id=return_request.id,
                    note=f"Returned stock for {order_item.product.name} restored after QC approval",
                    actor=actor,
                )
                _refresh_low_stock_alert(stock_item)
    return return_request
