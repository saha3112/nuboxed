from celery import shared_task
from django.utils import timezone


@shared_task(name="marketplace.process_jobs")
def process_marketplace_jobs():
    """Run the fallback poller and queued stock/product/order jobs."""
    from django.core.management import call_command
    call_command("process_marketplace_jobs")
    return "marketplace jobs processed"


@shared_task(name="marketplace.refresh_production_tokens")
def refresh_production_tokens():
    """Refresh Amazon Production LWA access tokens before their 60-minute TTL.

    Amazon normally keeps the refresh token stable; the rotating value is the
    short-lived access token.  If Amazon rotates the refresh token, the driver
    stores the new encrypted value inside the Production profile.
    """
    from apps.marketplace.models import MarketplaceConnection
    from apps.marketplace.drivers.providers import get_driver

    refreshed = 0
    failed = 0
    connections = MarketplaceConnection.objects.filter(connector__code="amazon")
    for connection in connections:
        credentials = connection.credentials or {}
        production = credentials.get("production")
        if not isinstance(production, dict):
            # Legacy connections used the top-level environment/token fields.
            if credentials.get("environment") != "production":
                continue
        try:
            get_driver(connection).refresh_token(environment="production")
            refreshed += 1
        except Exception as exc:
            failed += 1
            connection.error_message = str(exc)
            connection.status = connection.STATUS_ERROR
            profile = dict(credentials.get("production") or {})
            profile["last_refresh_result"] = "failed"
            profile["last_refresh_failed_at"] = timezone.now().isoformat()
            profile["last_refresh_error"] = str(exc)
            credentials["production"] = profile
            connection.credentials = credentials
            connection.save(update_fields=["error_message", "status", "credentials", "updated_at"])
    return {"refreshed": refreshed, "failed": failed}
