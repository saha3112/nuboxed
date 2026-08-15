import json
from urllib.request import Request, urlopen

from celery import shared_task
from django.conf import settings

from .device_presets import backfill_device_model_years, rebuild_device_options_and_variants, seed_device_catalog, sync_catalog_payload


@shared_task(name="catalog.sync_device_catalog")
def sync_device_catalog():
    """Refresh the built-in catalogue and merge an optional live device feed."""
    stats = seed_device_catalog()
    feed_url = getattr(settings, "DEVICE_CATALOG_FEED_URL", "").strip()
    if feed_url:
        request = Request(feed_url, headers={"User-Agent": "Nuboxed-Device-Catalog/1.0"})
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        feed_stats = sync_catalog_payload(payload)
        for key, value in feed_stats.items():
            stats[key] = stats.get(key, 0) + value
    year_stats = backfill_device_model_years()
    stats.update(rebuild_device_options_and_variants())
    stats.update(year_stats)
    return {"status": "synced", "feed_configured": bool(feed_url), **stats}
