from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.marketplace.views import (
    MarketplaceConnectorViewSet,
    MarketplaceConnectionViewSet,
    MarketplaceSyncJobViewSet,
    MarketplaceConflictLogViewSet,
    webhook_listener,
    sync_dashboard,
    trigger_cron_fallback
)

router = DefaultRouter()
router.register(r"connectors", MarketplaceConnectorViewSet, basename="connector")
router.register(r"connections", MarketplaceConnectionViewSet, basename="connection")
router.register(r"jobs", MarketplaceSyncJobViewSet, basename="sync-job")
router.register(r"conflicts", MarketplaceConflictLogViewSet, basename="conflict-log")

urlpatterns = [
    path("", include(router.urls)),
    path("webhooks/<str:connector_code>/", webhook_listener, name="marketplace-webhook"),
    path("dashboard/", sync_dashboard, name="marketplace-dashboard"),
    path("cron-fallback/", trigger_cron_fallback, name="marketplace-cron-fallback"),
]
