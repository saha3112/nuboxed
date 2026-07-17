from django.http import Http404
from django.utils.dateparse import parse_date
from rest_framework import generics, permissions, response, status
from rest_framework.views import APIView

from apps.orders.models import Order
from apps.rbac.permissions import CommerceAccessPermission
from apps.shipments.models import (
    CourierBooking,
    CourierCredential,
    CourierCountryServiceability,
    CourierPerformanceReport,
    CourierPickupSchedule,
    CourierRule,
    CourierReturnPickup,
    CourierServiceabilityRule,
    CourierShipmentEvent,
    CourierPartner,
    FulfillmentRecord,
    Shipment,
)
from apps.shipments.services import (
    build_fulfillment_for_order,
    check_courier_serviceability,
    create_courier_shipment,
    create_courier_shipment_label,
    generate_courier_performance_report,
    generate_courier_tracking_snapshot,
    initiate_reverse_logistics,
    process_courier_delivery_webhook,
    schedule_courier_pickup,
)

from .serializers import (
    CourierBookingSerializer,
    CourierCountryServiceabilitySerializer,
    CourierCredentialSerializer,
    CourierLabelRequestSerializer,
    CourierPerformanceReportSerializer,
    CourierPickupScheduleCreateSerializer,
    CourierPartnerSerializer,
    CourierRuleSerializer,
    CourierServiceabilityCheckSerializer,
    CourierServiceabilityRuleSerializer,
    CourierShipmentCreateSerializer,
    FulfillmentRecordSerializer,
    PickupScheduleSerializer,
    ReturnPickupSerializer,
    ShipmentSerializer,
    ShipmentEventSerializer,
    TrackingSnapshotSerializer,
    WebhookSerializer,
)


class ShipmentsSuperAdminMixin:
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["shipments.manage"]


class CourierPartnerListCreateView(ShipmentsSuperAdminMixin, generics.ListCreateAPIView):
    queryset = CourierPartner.objects.all().order_by("name")
    serializer_class = CourierPartnerSerializer


class CourierCredentialListCreateView(ShipmentsSuperAdminMixin, generics.ListCreateAPIView):
    queryset = CourierCredential.objects.select_related("courier_partner").all()
    serializer_class = CourierCredentialSerializer


class CountryServiceabilityListCreateView(ShipmentsSuperAdminMixin, generics.ListCreateAPIView):
    queryset = CourierCountryServiceability.objects.select_related("courier_partner").all()
    serializer_class = CourierCountryServiceabilitySerializer


class CourierServiceabilityRuleListCreateView(ShipmentsSuperAdminMixin, generics.ListCreateAPIView):
    queryset = CourierServiceabilityRule.objects.select_related("courier_partner", "store").all()
    serializer_class = CourierServiceabilityRuleSerializer


class CourierRuleListCreateView(ShipmentsSuperAdminMixin, generics.ListCreateAPIView):
    queryset = CourierRule.objects.select_related("courier_partner").all()
    serializer_class = CourierRuleSerializer


class ShipmentListView(ShipmentsSuperAdminMixin, generics.ListAPIView):
    queryset = Shipment.objects.select_related("order", "courier_partner").all()
    serializer_class = ShipmentSerializer


class ShipmentDetailView(ShipmentsSuperAdminMixin, generics.RetrieveAPIView):
    queryset = Shipment.objects.select_related("order", "courier_partner").all()
    serializer_class = ShipmentSerializer
    lookup_url_kwarg = "shipment_id"


class ShipmentEventListView(ShipmentsSuperAdminMixin, generics.ListAPIView):
    queryset = CourierShipmentEvent.objects.select_related("shipment").all()
    serializer_class = ShipmentEventSerializer


class CourierBookingListView(ShipmentsSuperAdminMixin, generics.ListAPIView):
    queryset = CourierBooking.objects.select_related("order", "shipment", "courier_partner").all()
    serializer_class = CourierBookingSerializer


class FulfillmentRecordListView(ShipmentsSuperAdminMixin, generics.ListAPIView):
    queryset = FulfillmentRecord.objects.select_related("order", "offline_sale", "connector").all()
    serializer_class = FulfillmentRecordSerializer


class ServiceabilityCheckView(ShipmentsSuperAdminMixin, APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = CourierServiceabilityCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.save()
        return response.Response(data)


class ShipmentCreateView(ShipmentsSuperAdminMixin, APIView):
    def post(self, request):
        serializer = CourierShipmentCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        payload = serializer.save()
        return response.Response(payload, status=status.HTTP_201_CREATED)


class ShipmentLabelView(ShipmentsSuperAdminMixin, APIView):
    def post(self, request, shipment_id):
        shipment = Shipment.objects.filter(id=shipment_id).first()
        if not shipment:
            raise Http404("Shipment not found.")
        serializer = CourierLabelRequestSerializer(
            data={"shipment_id": shipment_id},
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        payload = serializer.save()
        return response.Response(payload)


class PickupScheduleCreateView(ShipmentsSuperAdminMixin, APIView):
    def post(self, request):
        serializer = CourierPickupScheduleCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        pickup = serializer.save()
        return response.Response(PickupScheduleSerializer(pickup).data, status=status.HTTP_201_CREATED)


class ReturnPickupCreateView(ShipmentsSuperAdminMixin, APIView):
    def post(self, request):
        order_id = request.data.get("order_id")
        reason = request.data.get("reason", "")
        order = Order.objects.filter(id=order_id).first()
        if not order:
            raise Http404("Order not found.")
        pickup = initiate_reverse_logistics(order, reason=reason, actor=request.user)
        return response.Response(ReturnPickupSerializer(pickup).data, status=status.HTTP_201_CREATED)


class TrackingSnapshotView(ShipmentsSuperAdminMixin, APIView):
    def get(self, request, shipment_id=None):
        identifier = {"shipment_id": shipment_id} if shipment_id else {"tracking_number": request.query_params.get("tracking_number", "")}
        serializer = TrackingSnapshotSerializer(data=identifier)
        serializer.is_valid(raise_exception=True)
        payload = serializer.save()
        return response.Response(payload)


class CourierWebhookView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = WebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        tracking_reference = payload.get("tracking_number") or payload.get("awb_number") or payload.get("shipment_id")
        shipment = Shipment.objects.select_related("courier_partner").filter(
            tracking_number=tracking_reference
        ).first()
        if shipment is None:
            raise Http404("Shipment not found.")
        courier_partner = shipment.courier_partner
        if courier_partner is not None:
            secret = payload.get("token") or request.headers.get("X-Courier-Token") or ""
            stored_secret = (
                CourierCredential.objects.filter(
                    courier_partner=courier_partner,
                    credential_type=CourierCredential.CREDENTIAL_WEBHOOK_SECRET,
                    is_active=True,
                )
                .values_list("value", flat=True)
                .first()
            )
            if stored_secret and secret != stored_secret:
                return response.Response({"detail": "Invalid webhook token."}, status=status.HTTP_403_FORBIDDEN)
        updated = process_courier_delivery_webhook(payload, actor=None)
        return response.Response(generate_courier_tracking_snapshot(updated))


class CourierPerformanceReportListView(ShipmentsSuperAdminMixin, APIView):
    def get(self, request):
        partner_id = request.query_params.get("courier_partner_id")
        period_start = parse_date(request.query_params.get("period_start", ""))
        period_end = parse_date(request.query_params.get("period_end", ""))
        if not partner_id or not period_start or not period_end:
            return response.Response(
                {"detail": "courier_partner_id, period_start and period_end are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from apps.shipments.models import CourierPartner

        courier_partner = CourierPartner.objects.filter(id=partner_id).first()
        if courier_partner is None:
            raise Http404("Courier partner not found.")
        report = generate_courier_performance_report(courier_partner, period_start, period_end)
        return response.Response(CourierPerformanceReportSerializer(report).data)


class CourierReturnPickupListView(ShipmentsSuperAdminMixin, generics.ListAPIView):
    queryset = CourierReturnPickup.objects.select_related("order", "shipment", "courier_partner").all()
    serializer_class = ReturnPickupSerializer
