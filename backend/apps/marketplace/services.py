import hashlib
import logging
from typing import Dict, Any, List
from django.db import transaction
from django.utils import timezone
from django.db.models import Count, Q
from django.utils.dateparse import parse_datetime
from decimal import Decimal

from apps.marketplace.models import (
    MarketplaceConnector,
    MarketplaceConnection,
    MarketplaceSyncJob,
    MarketplaceConflictLog,
    MarketplaceWebhookEvent
    , AmazonOrderTracking, AmazonOrderItemTracking, MarketplaceListing
)
from apps.marketplace.drivers.providers import get_driver
from apps.notifications.services import send_notification_event
from apps.inventory.models import StockItem, StockLedger
from apps.inventory.services import ensure_default_warehouse

logger = logging.getLogger(__name__)


@transaction.atomic
def configure_connector(code: str, name: str, connector_type: str, status: str = "draft", config: Dict[str, Any] = None) -> MarketplaceConnector:
    """
    Super Admin configures or updates a global connector.
    """
    connector, created = MarketplaceConnector.objects.update_or_create(
        code=code,
        defaults={
            "name": name,
            "connector_type": connector_type,
            "status": status,
            "config": config or {},
        }
    )
    return connector


@transaction.atomic
def create_connection(connector: MarketplaceConnector, name: str, credentials: Dict[str, Any], retailer=None, store=None) -> MarketplaceConnection:
    """
    Configures an instance of a connection to a specific marketplace account.
    Only Super Admin invokes this on behalf of the system or retailers.
    """
    connection = MarketplaceConnection.objects.create(
        connector=connector,
        retailer=retailer,
        store=store,
        name=name,
        credentials=credentials,
        status=MarketplaceConnection.STATUS_ACTIVE
    )
    
    # Refresh OAuth token initially if refresh token is present
    driver = get_driver(connection)
    try:
        driver.refresh_token()
    except Exception as e:
        logger.exception("Initial token refresh failed.")
        connection.status = MarketplaceConnection.STATUS_ERROR
        connection.error_message = str(e)
        connection.save(update_fields=["status", "error_message"])

    return connection


@transaction.atomic
def enqueue_sync_job(connection: MarketplaceConnection, job_type: str, direction: str, payload: Dict[str, Any] = None) -> MarketplaceSyncJob:
    """
    Puts a sync event in the queue.
    """
    if not payload:
        existing = MarketplaceSyncJob.objects.filter(
            connection=connection,
            job_type=job_type,
            direction=direction,
            status__in=(MarketplaceSyncJob.STATUS_PENDING, MarketplaceSyncJob.STATUS_PROCESSING),
        ).order_by("created_at").first()
        if existing:
            return existing
    job = MarketplaceSyncJob.objects.create(
        connection=connection,
        job_type=job_type,
        direction=direction,
        payload=payload or {},
        status=MarketplaceSyncJob.STATUS_PENDING
    )
    # Local development often runs only Django and has no Redis/Celery
    # worker. Process this exact job after commit instead of invoking the
    # broad management poller, which could enqueue unrelated stale jobs and
    # make a manual Sync Now appear slow.
    from django.conf import settings
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        transaction.on_commit(lambda: process_sync_job(job))
    return job


def enqueue_product_stock_sync(product, variant=None):
    """Queue outbound stock updates after any local stock mutation.

    The worker/management command can process these jobs asynchronously; the
    helper deliberately only queues work so checkout and warehouse screens do
    not block on Amazon's rate-limited API.
    """
    connections = MarketplaceConnection.objects.filter(
        connector__code="amazon", status=MarketplaceConnection.STATUS_ACTIVE,
    ).filter(Q(retailer_id=product.retailer_id) | Q(retailer__isnull=True))
    jobs = []
    for connection in connections:
        payload = {"items": [{"sku": getattr(variant, "sku", None) or product.sku}]}
        jobs.append(enqueue_sync_job(connection, MarketplaceSyncJob.TYPE_STOCK_SYNC, MarketplaceSyncJob.DIRECTION_OUTBOUND, payload))
    return jobs


def sync_product_amazon_mapping(product, seller_sku="", asin="", variant=None):
    """Save the product's explicit Amazon identity and queue its first sync.

    Amazon seller SKUs are marketplace identities and do not have to equal a
    Nuboxed SKU. Keeping this mapping on MarketplaceListing lets admin and
    retailer product editors use the same product record without changing the
    storefront SKU.
    """
    connections = MarketplaceConnection.objects.filter(connector__code="amazon")
    saved = []
    for connection in connections:
        credentials = connection.credentials or {}
        environment = credentials.get("environment", "sandbox")
        profile = credentials.get(environment) if isinstance(credentials.get(environment), dict) else credentials
        marketplace_id = (profile or {}).get("marketplace_id") or credentials.get("marketplace_id", "")
        listing = MarketplaceListing.objects.filter(connection=connection, product=product, variant=variant).first()
        seller_value = (seller_sku or (listing.seller_sku if listing else "") or getattr(variant, "sku", "") or product.sku).strip()
        asin_value = (asin or (listing.external_listing_id if listing else "")).strip()
        if not marketplace_id:
            continue
        conflicting = MarketplaceListing.objects.filter(connection=connection, seller_sku=seller_value).exclude(product=product, variant=variant).first()
        if conflicting:
            if listing:
                listing.last_error = f"Amazon Seller SKU {seller_value} is already mapped to another Nuboxed product."
                listing.status = "pending"
                listing.save(update_fields=["last_error", "status", "updated_at"])
            continue
        if listing:
            listing.seller_sku = seller_value
            listing.external_listing_id = asin_value
            listing.marketplace_id = marketplace_id
            listing.status = "pending"
            listing.last_error = ""
            listing.save(update_fields=["seller_sku", "external_listing_id", "marketplace_id", "status", "last_error", "updated_at"])
        else:
            listing = MarketplaceListing.objects.create(connection=connection, product=product, variant=variant, seller_sku=seller_value, external_listing_id=asin_value, marketplace_id=marketplace_id, status="pending")
        saved.append(listing)
        if (profile or {}).get("auto_sync", credentials.get("auto_sync", True)) is not False and connection.status == MarketplaceConnection.STATUS_ACTIVE:
            for job_type, direction in ((MarketplaceSyncJob.TYPE_PRODUCT_SYNC, MarketplaceSyncJob.DIRECTION_OUTBOUND), (MarketplaceSyncJob.TYPE_STOCK_SYNC, MarketplaceSyncJob.DIRECTION_OUTBOUND)):
                exists = MarketplaceSyncJob.objects.filter(connection=connection, job_type=job_type, direction=direction, status__in=(MarketplaceSyncJob.STATUS_PENDING, MarketplaceSyncJob.STATUS_PROCESSING)).exists()
                if not exists:
                    enqueue_sync_job(connection, job_type, direction, {"items": [{"sku": seller_value}]})
    return saved


@transaction.atomic
def apply_amazon_order_inventory(connection, tracking, order_items):
    """Deduct an imported Amazon sale once and queue the new Amazon quantity.

    Amazon order imports are repeated by design.  The stock ledger reference
    makes this operation idempotent, so importing the same order again never
    deducts the same quantity twice.  Cancellation creates one compensating
    restore movement.
    """
    changed = []
    cancelled = str(tracking.amazon_order_status or "").lower() in {"canceled", "cancelled"}
    for index, item in enumerate(order_items or []):
        product = getattr(item, "product", None)
        if not product or not item.quantity:
            continue
        warehouse = None
        listing = MarketplaceListing.objects.filter(
            connection=connection, seller_sku=item.seller_sku,
        ).select_related("fulfillment_location").first()
        if listing and listing.fulfillment_location_id:
            warehouse = listing.fulfillment_location
        if warehouse is None:
            warehouse = ensure_default_warehouse(retailer=product.retailer, store=item.store or product.store)
        stock_item, _ = StockItem.objects.select_for_update().get_or_create(
            warehouse=warehouse,
            product=product,
            variant=item.variant,
            defaults={"low_stock_threshold": 0},
        )
        reference_id = hashlib.sha256(
            f"{tracking.external_order_id}:{item.seller_sku}:{index}".encode("utf-8")
        ).hexdigest()
        sale_exists = StockLedger.objects.filter(
            reference_type="amazon_order",
            reference_id=reference_id,
            movement_type=StockLedger.TYPE_ONLINE_SALE,
        ).exists()
        restore_exists = StockLedger.objects.filter(
            reference_type="amazon_order_cancel",
            reference_id=reference_id,
            movement_type=StockLedger.TYPE_CANCEL_RESTORE,
        ).exists()
        if cancelled:
            if sale_exists and not restore_exists:
                stock_item.on_hand_quantity += item.quantity
                stock_item.save(update_fields=["on_hand_quantity", "updated_at"])
                StockLedger.objects.create(
                    warehouse=warehouse, stock_item=stock_item,
                    product=product, variant=item.variant,
                    movement_type=StockLedger.TYPE_CANCEL_RESTORE,
                    quantity_delta=item.quantity,
                    reference_type="amazon_order_cancel",
                    reference_id=reference_id,
                    note=f"Restored cancelled Amazon order {tracking.external_order_id}",
                )
                changed.append((product, item.variant))
            continue
        if sale_exists:
            continue
        stock_item.on_hand_quantity = max(0, stock_item.on_hand_quantity - item.quantity)
        stock_item.save(update_fields=["on_hand_quantity", "updated_at"])
        StockLedger.objects.create(
            warehouse=warehouse, stock_item=stock_item,
            product=product, variant=item.variant,
            movement_type=StockLedger.TYPE_ONLINE_SALE,
            quantity_delta=-item.quantity,
            reference_type="amazon_order",
            reference_id=reference_id,
            note=f"Amazon sale {tracking.external_order_id}",
        )
        changed.append((product, item.variant))

    # Queue one outbound stock reconciliation for every changed variant. The
    # normal marketplace worker/eager local runner performs the Amazon update.
    for product, variant in changed:
        enqueue_product_stock_sync(product, variant)
    return changed


@transaction.atomic
def record_amazon_orders(connection, orders):
    """Upsert Amazon orders and attribute each line to its Nuboxed store."""
    saved = []
    for payload in orders or []:
        external_id = payload.get("AmazonOrderId") or payload.get("amazon_order_id") or payload.get("external_order_id")
        if not external_id:
            continue
        total = payload.get("OrderTotal") or {}
        tracking, _ = AmazonOrderTracking.objects.update_or_create(
            connection=connection, external_order_id=str(external_id),
            defaults={
                "amazon_order_status": payload.get("OrderStatus", payload.get("status", "")),
                "fulfillment_status": payload.get("FulfillmentChannel", payload.get("fulfillment_status", "")),
                "marketplace_id": payload.get("MarketplaceId", ""),
                "purchase_date": parse_datetime(payload.get("PurchaseDate", "")) if payload.get("PurchaseDate") else None,
                "order_total": Decimal(str(total.get("Amount", payload.get("amount", "0")) or "0")),
                "currency_code": total.get("CurrencyCode", payload.get("currency", "")),
                "shipping_city": (payload.get("ShippingAddress") or {}).get("City", ""),
                "shipping_country_code": (payload.get("ShippingAddress") or {}).get("CountryCode", ""),
                "raw_payload": payload, "last_seen_at": timezone.now(),
                "retailer": connection.retailer,
                "store": connection.store,
            },
        )
        tracking.items.all().delete()
        stores, retailers = set(), set()
        for item in payload.get("OrderItems", payload.get("items", [])) or []:
            sku = item.get("SellerSKU", item.get("seller_sku", ""))
            listing = MarketplaceListing.objects.filter(connection=connection, seller_sku=sku).select_related("product", "variant", "product__store", "product__retailer").first()
            product = listing.product if listing else None
            variant = listing.variant if listing else None
            store = product.store if product else None
            retailer = product.retailer if product else connection.retailer
            if store: stores.add(store.pk)
            if retailer: retailers.add(retailer.pk)
            item_total = item.get("ItemPrice", {}).get("Amount", item.get("item_total")) if isinstance(item.get("ItemPrice", item.get("item_total")), dict) else item.get("item_total")
            AmazonOrderItemTracking.objects.create(
                tracking_order=tracking, product=product, variant=variant, retailer=retailer, store=store,
                seller_sku=sku, title=item.get("Title", item.get("title", "")), quantity=int(item.get("QuantityOrdered", item.get("quantity", 0)) or 0),
                item_total=Decimal(str(item_total or "0")), raw_payload=item,
            )
        tracking.retailer_id = next(iter(retailers)) if len(retailers) == 1 else (connection.retailer_id if not retailers else None)
        tracking.store_id = next(iter(stores)) if len(stores) == 1 else (connection.store_id if not stores else None)
        tracking.attribution_status = "attributed" if len(stores) == 1 else "multiple_stores" if len(stores) > 1 else "pending_items"
        tracking.imported_at = tracking.imported_at or timezone.now()
        tracking.save(update_fields=["retailer", "store", "attribution_status", "imported_at", "updated_at"])
        apply_amazon_order_inventory(connection, tracking, list(tracking.items.all()))
        saved.append(tracking)
    return saved


def process_sync_job(job: MarketplaceSyncJob) -> MarketplaceSyncJob:
    """
    Executes a sync job using the mapped driver, increments retries on failure,
    handles OAuth expiration, and records execution results or conflict logs.
    """
    job.status = MarketplaceSyncJob.STATUS_PROCESSING
    job.save(update_fields=["status", "updated_at"])

    connection = job.connection
    driver = get_driver(connection)

    # Check OAuth token expiration
    if connection.token_expires_at and connection.token_expires_at <= timezone.now():
        try:
            driver.refresh_token()
        except Exception as e:
            job.status = MarketplaceSyncJob.STATUS_FAILED
            job.error_message = f"OAuth token refresh failed: {str(e)}"
            job.retry_count += 1
            job.save(update_fields=["status", "error_message", "retry_count", "updated_at"])
            return job

    try:
        # Resolve action
        job_payload = dict(job.payload or {})
        job_payload["_direction"] = job.direction
        if job.job_type == MarketplaceSyncJob.TYPE_PRODUCT_SYNC:
            result = driver.import_products(job_payload) if job.direction == MarketplaceSyncJob.DIRECTION_INBOUND and connection.connector.code.lower() == "amazon" else driver.sync_products(job_payload)
        elif job.job_type == MarketplaceSyncJob.TYPE_PRICE_SYNC:
            result = driver.sync_prices(job_payload)
        elif job.job_type == MarketplaceSyncJob.TYPE_STOCK_SYNC:
            result = driver.sync_stock(job_payload)
        elif job.job_type == MarketplaceSyncJob.TYPE_ORDER_IMPORT:
            result = driver.import_orders(job_payload)
            if connection.connector.code.lower() == "amazon":
                tracked = record_amazon_orders(connection, result.get("imported_orders", []))
                result["tracked_count"] = len(tracked)
        elif job.job_type == MarketplaceSyncJob.TYPE_RETURN_SYNC:
            result = driver.sync_returns(job.payload)
        elif job.job_type == MarketplaceSyncJob.TYPE_REFUND_SYNC:
            result = driver.sync_refunds(job.payload)
        elif job.job_type == MarketplaceSyncJob.TYPE_SETTLEMENT_SYNC:
            result = driver.sync_settlements(job.payload)
        else:
            raise ValueError(f"Unknown job type: {job.job_type}")

        job.status = MarketplaceSyncJob.STATUS_COMPLETED
        job.result = result
        job.save(update_fields=["status", "result", "updated_at"])

        # Update connection last sync timestamp
        connection.last_sync_at = timezone.now()
        connection.status = MarketplaceConnection.STATUS_ACTIVE
        connection.error_message = ""
        connection.save(update_fields=["last_sync_at", "status", "error_message"])

    except Exception as e:
        logger.exception(f"Sync job {job.id} failed.")
        job.status = MarketplaceSyncJob.STATUS_FAILED
        job.error_message = str(e)
        job.retry_count += 1
        
        # Backoff logic
        job.run_at = timezone.now() + timezone.timedelta(minutes=2 ** job.retry_count)
        job.save(update_fields=["status", "error_message", "retry_count", "run_at", "updated_at"])

        connection.status = MarketplaceConnection.STATUS_ERROR
        connection.error_message = f"Sync job failed: {str(e)}"
        connection.save(update_fields=["status", "error_message"])
        
        user = connection.retailer.account.owner if connection.retailer and getattr(connection.retailer, 'account', None) else None
        send_notification_event(
            event_name="marketplace_sync_error",
            context={"connector_code": connection.connector.code, "error": str(e)},
            user=user
        )

    return job


@transaction.atomic
def resolve_conflict(conflict_id: str, strategy: str, resolved_by) -> MarketplaceConflictLog:
    """
    Applies resolution strategy to clear conflict logs.
    """
    conflict = MarketplaceConflictLog.objects.get(id=conflict_id)
    conflict.resolution_strategy = strategy
    conflict.is_resolved = True
    conflict.resolved_at = timezone.now()
    conflict.resolved_by = resolved_by
    conflict.save(update_fields=["resolution_strategy", "is_resolved", "resolved_at", "resolved_by", "updated_at"])

    # Enqueue a sync retry job depending on the resolution strategy
    if strategy == MarketplaceConflictLog.STRATEGY_LOCAL:
        # Push local state to external marketplace
        enqueue_sync_job(
            connection=conflict.connection,
            job_type=MarketplaceSyncJob.TYPE_PRODUCT_SYNC if conflict.entity_type == "product" else MarketplaceSyncJob.TYPE_STOCK_SYNC,
            direction=MarketplaceSyncJob.DIRECTION_OUTBOUND,
            payload={"entity_id": conflict.entity_id, "data": conflict.local_data}
        )
    elif strategy == MarketplaceConflictLog.STRATEGY_EXTERNAL:
        # Pull external state to local store
        enqueue_sync_job(
            connection=conflict.connection,
            job_type=MarketplaceSyncJob.TYPE_PRODUCT_SYNC if conflict.entity_type == "product" else MarketplaceSyncJob.TYPE_STOCK_SYNC,
            direction=MarketplaceSyncJob.DIRECTION_INBOUND,
            payload={"entity_id": conflict.entity_id, "data": conflict.external_data}
        )

    return conflict


@transaction.atomic
def receive_webhook_event(connector_code: str, headers: Dict[str, Any], payload: Dict[str, Any]) -> MarketplaceWebhookEvent:
    """
    Persists an incoming webhook event.
    """
    return MarketplaceWebhookEvent.objects.create(
        connector_code=connector_code,
        headers=headers,
        payload=payload,
        status=MarketplaceWebhookEvent.STATUS_PENDING
    )


def process_webhook_event(event: MarketplaceWebhookEvent) -> MarketplaceWebhookEvent:
    """
    Invokes the driver webhook handler and transitions event status.
    """
    event.status = MarketplaceWebhookEvent.STATUS_PROCESSED
    event.processed_at = timezone.now()

    # Find any active connection for this connector code
    connection = MarketplaceConnection.objects.filter(connector__code=event.connector_code, status=MarketplaceConnection.STATUS_ACTIVE).first()
    if not connection:
        event.status = MarketplaceWebhookEvent.STATUS_FAILED
        event.error_message = f"No active connection found for connector code: {event.connector_code}"
        event.save(update_fields=["status", "error_message", "processed_at", "updated_at"])
        return event

    driver = get_driver(connection)
    try:
        driver.handle_webhook(event.headers, event.payload)
        event.save(update_fields=["status", "processed_at", "updated_at"])
    except Exception as e:
        event.status = MarketplaceWebhookEvent.STATUS_FAILED
        event.error_message = str(e)
        event.save(update_fields=["status", "error_message", "processed_at", "updated_at"])

    return event


def cron_fallback_sync() -> List[MarketplaceSyncJob]:
    """
    Periodic backup task that enqueues inbound imports for all active accounts.
    Failsafe for webhook drops.
    """
    enqueued_jobs = []
    active_connections = MarketplaceConnection.objects.filter(status=MarketplaceConnection.STATUS_ACTIVE)
    
    for conn in active_connections:
        credentials = conn.credentials or {}
        if credentials.get("auto_sync", True) is False:
            continue
        # Keep the automatic loop idempotent: do not create another copy while
        # the previous job is still pending or processing.
        # Keep both directions automatic: local products/stock go to Amazon,
        # while Amazon listings/stock/orders come back into Nuboxed.
        for job_type, direction in ((MarketplaceSyncJob.TYPE_PRODUCT_SYNC, MarketplaceSyncJob.DIRECTION_OUTBOUND), (MarketplaceSyncJob.TYPE_PRODUCT_SYNC, MarketplaceSyncJob.DIRECTION_INBOUND), (MarketplaceSyncJob.TYPE_STOCK_SYNC, MarketplaceSyncJob.DIRECTION_OUTBOUND), (MarketplaceSyncJob.TYPE_STOCK_SYNC, MarketplaceSyncJob.DIRECTION_INBOUND), (MarketplaceSyncJob.TYPE_ORDER_IMPORT, MarketplaceSyncJob.DIRECTION_INBOUND)):
            exists = MarketplaceSyncJob.objects.filter(connection=conn, job_type=job_type, direction=direction, status__in=(MarketplaceSyncJob.STATUS_PENDING, MarketplaceSyncJob.STATUS_PROCESSING)).exists()
            if not exists:
                enqueued_jobs.append(enqueue_sync_job(conn, job_type, direction))
        
    return enqueued_jobs


def get_sync_dashboard_stats() -> Dict[str, Any]:
    """
    Gathers metrics for the Sync Dashboard.
    """
    job_stats = MarketplaceSyncJob.objects.values("status").annotate(count=Count("id"))
    connection_stats = MarketplaceConnection.objects.values("status").annotate(count=Count("id"))
    conflict_stats = MarketplaceConflictLog.objects.aggregate(
        total_conflicts=Count("id"),
        resolved=Count("id", filter=Q(is_resolved=True)),
        unresolved=Count("id", filter=Q(is_resolved=False)),
    )

    stats = {
        "connections": {item["status"]: item["count"] for item in connection_stats},
        "sync_jobs": {item["status"]: item["count"] for item in job_stats},
        "conflicts": conflict_stats
    }
    return stats
