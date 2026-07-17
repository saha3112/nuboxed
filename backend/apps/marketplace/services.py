import logging
from typing import Dict, Any, List
from django.db import transaction
from django.utils import timezone
from django.db.models import Count, Q

from apps.marketplace.models import (
    MarketplaceConnector,
    MarketplaceConnection,
    MarketplaceSyncJob,
    MarketplaceConflictLog,
    MarketplaceWebhookEvent
)
from apps.marketplace.drivers.providers import get_driver
from apps.notifications.services import send_notification_event

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
    return MarketplaceSyncJob.objects.create(
        connection=connection,
        job_type=job_type,
        direction=direction,
        payload=payload or {},
        status=MarketplaceSyncJob.STATUS_PENDING
    )


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
        if job.job_type == MarketplaceSyncJob.TYPE_PRODUCT_SYNC:
            result = driver.sync_products(job.payload)
        elif job.job_type == MarketplaceSyncJob.TYPE_PRICE_SYNC:
            result = driver.sync_prices(job.payload)
        elif job.job_type == MarketplaceSyncJob.TYPE_STOCK_SYNC:
            result = driver.sync_stock(job.payload)
        elif job.job_type == MarketplaceSyncJob.TYPE_ORDER_IMPORT:
            result = driver.import_orders(job.payload)
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
        # Enqueue order imports and product syncs
        enqueued_jobs.append(enqueue_sync_job(conn, MarketplaceSyncJob.TYPE_ORDER_IMPORT, MarketplaceSyncJob.DIRECTION_INBOUND))
        enqueued_jobs.append(enqueue_sync_job(conn, MarketplaceSyncJob.TYPE_STOCK_SYNC, MarketplaceSyncJob.DIRECTION_INBOUND))
        
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
