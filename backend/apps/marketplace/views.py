from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.marketplace.models import (
    MarketplaceConnector,
    MarketplaceConnection,
    MarketplaceSyncJob,
    MarketplaceConflictLog,
    MarketplaceWebhookEvent
)
from apps.marketplace.serializers import (
    MarketplaceConnectorSerializer,
    MarketplaceConnectionSerializer,
    MarketplaceConnectionCreateSerializer,
    MarketplaceSyncJobSerializer,
    MarketplaceConflictLogSerializer,
    ResolveConflictInputSerializer,
    MarketplaceWebhookEventSerializer
)
from apps.marketplace.services import (
    configure_connector,
    create_connection,
    enqueue_sync_job,
    process_sync_job,
    resolve_conflict,
    receive_webhook_event,
    process_webhook_event,
    get_sync_dashboard_stats,
    cron_fallback_sync
)
from apps.marketplace.drivers.providers import get_driver


class IsSuperAdminOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow Super Admins to edit/configure connectors.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return request.user and request.user.is_authenticated and request.user.is_super_admin


class IsSuperAdmin(permissions.BasePermission):
    """
    Custom permission to only allow Super Admins to write/configure connection details.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_super_admin


class MarketplaceConnectorViewSet(viewsets.ModelViewSet):
    queryset = MarketplaceConnector.objects.all()
    serializer_class = MarketplaceConnectorSerializer
    permission_classes = [IsSuperAdminOrReadOnly]


class MarketplaceConnectionViewSet(viewsets.ModelViewSet):
    queryset = MarketplaceConnection.objects.all()
    permission_classes = [IsSuperAdmin]

    def get_serializer_class(self):
        if self.action == "create":
            return MarketplaceConnectionCreateSerializer
        return MarketplaceConnectionSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            conn = create_connection(
                connector=serializer.validated_data["connector"],
                name=serializer.validated_data["name"],
                credentials=serializer.validated_data["credentials"],
                retailer=serializer.validated_data.get("retailer"),
                store=serializer.validated_data.get("store")
            )
            res_serializer = MarketplaceConnectionSerializer(conn)
            return Response(res_serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="refresh-token")
    def refresh_token(self, request, pk=None):
        conn = self.get_object()
        driver = get_driver(conn)
        try:
            res = driver.refresh_token()
            return Response(res)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="enqueue-job")
    def enqueue_job(self, request, pk=None):
        conn = self.get_object()
        job_type = request.data.get("job_type")
        direction = request.data.get("direction", MarketplaceSyncJob.DIRECTION_INBOUND)
        payload = request.data.get("payload", {})

        if not job_type:
            return Response({"detail": "job_type is required"}, status=status.HTTP_400_BAD_REQUEST)

        job = enqueue_sync_job(conn, job_type, direction, payload)
        serializer = MarketplaceSyncJobSerializer(job)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class MarketplaceSyncJobViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MarketplaceSyncJob.objects.all()
    serializer_class = MarketplaceSyncJobSerializer
    permission_classes = [IsSuperAdmin]

    @action(detail=True, methods=["post"], url_path="trigger")
    def trigger_job(self, request, pk=None):
        job = get_object_or_404(MarketplaceSyncJob, id=pk)
        try:
            job = process_sync_job(job)
            serializer = self.get_serializer(job)
            return Response(serializer.data)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class MarketplaceConflictLogViewSet(viewsets.ModelViewSet):
    queryset = MarketplaceConflictLog.objects.all()
    serializer_class = MarketplaceConflictLogSerializer
    permission_classes = [IsSuperAdmin]

    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve_conflict_action(self, request, pk=None):
        conflict = self.get_object()
        serializer = ResolveConflictInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            resolved = resolve_conflict(
                conflict_id=conflict.id,
                strategy=serializer.validated_data["resolution_strategy"],
                resolved_by=request.user
            )
            res_serializer = self.get_serializer(resolved)
            return Response(res_serializer.data)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def webhook_listener(request, connector_code):
    """
    Inbound webhook receiver. Accepts headers and body, registers webhook event,
    and processes it.
    """
    headers = {k: v for k, v in request.headers.items()}
    payload = request.data
    event = receive_webhook_event(connector_code, headers, payload)
    processed_event = process_webhook_event(event)
    serializer = MarketplaceWebhookEventSerializer(processed_event)
    if processed_event.status == MarketplaceWebhookEvent.STATUS_FAILED:
        return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def sync_dashboard(request):
    """
    API endpoint returning statistics for the sync dashboard.
    """
    stats = get_sync_dashboard_stats()
    return Response(stats)


@api_view(["POST"])
@permission_classes([IsSuperAdmin])
def trigger_cron_fallback(request):
    """
    Manually triggers the cron fallback order import and stock sync failsafe.
    """
    jobs = cron_fallback_sync()
    serializer = MarketplaceSyncJobSerializer(jobs, many=True)
    return Response(serializer.data, status=status.HTTP_201_CREATED)
