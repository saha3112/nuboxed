from rest_framework import serializers

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
from apps.shipments.services import check_courier_serviceability, create_courier_shipment, generate_courier_tracking_snapshot


class CourierPartnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourierPartner
        fields = "__all__"


class CourierPartnerNestedSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    code = serializers.CharField()
    status = serializers.CharField()


class CourierCredentialSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourierCredential
        fields = "__all__"


class CourierCountryServiceabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = CourierCountryServiceability
        fields = "__all__"


class CourierServiceabilityRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourierServiceabilityRule
        fields = "__all__"


class CourierRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourierRule
        fields = "__all__"


class ShipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shipment
        fields = "__all__"


class ShipmentEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourierShipmentEvent
        fields = "__all__"


class CourierBookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourierBooking
        fields = "__all__"


class PickupScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourierPickupSchedule
        fields = "__all__"


class ReturnPickupSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourierReturnPickup
        fields = "__all__"


class FulfillmentRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = FulfillmentRecord
        fields = "__all__"


class CourierPerformanceReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourierPerformanceReport
        fields = "__all__"


class CourierServiceabilityCheckSerializer(serializers.Serializer):
    courier_partner_id = serializers.UUIDField(required=False)
    postal_code = serializers.CharField()
    country_code = serializers.CharField(max_length=2)
    store_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        from apps.shipments.models import CourierPartner
        from apps.stores.models import Store

        if attrs.get("courier_partner_id"):
            attrs["courier_partner"] = CourierPartner.objects.filter(id=attrs["courier_partner_id"]).first()
            if attrs["courier_partner"] is None:
                raise serializers.ValidationError({"courier_partner_id": "Invalid courier partner."})
        if attrs.get("store_id"):
            attrs["store"] = Store.objects.filter(id=attrs["store_id"]).first()
            if attrs["store"] is None:
                raise serializers.ValidationError({"store_id": "Invalid store."})
        return attrs

    def create(self, validated_data):
        result = check_courier_serviceability(
            postal_code=validated_data["postal_code"],
            country_code=validated_data["country_code"],
            courier_partner=validated_data.get("courier_partner"),
            store=validated_data.get("store"),
        )
        return {
            "serviceable": result["serviceable"],
            "pickup_available": result["pickup_available"],
            "cod_available": result["cod_available"],
            "handling_days": result["handling_days"],
            "transit_days": result["transit_days"],
            "courier_partner": result["courier_partner"].name if result["courier_partner"] else "",
            "postal_code": result["postal_code"],
            "country_code": result["country_code"],
        }


class CourierShipmentCreateSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    courier_partner_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        from apps.orders.models import Order
        from apps.shipments.models import CourierPartner

        order = Order.objects.filter(id=attrs["order_id"]).first()
        if not order:
            raise serializers.ValidationError({"order_id": "Invalid order."})
        if not order.is_website_order:
            raise serializers.ValidationError({"order_id": "Courier booking is only available for website orders."})
        attrs["order"] = order
        if attrs.get("courier_partner_id"):
            partner = CourierPartner.objects.filter(id=attrs["courier_partner_id"]).first()
            if not partner:
                raise serializers.ValidationError({"courier_partner_id": "Invalid courier partner."})
            attrs["courier_partner"] = partner
        return attrs

    def create(self, validated_data):
        shipment, booking = create_courier_shipment(
            validated_data["order"],
            courier_partner=validated_data.get("courier_partner"),
            actor=self.context["request"].user,
        )
        return {
            "shipment": ShipmentSerializer(shipment).data,
            "booking": CourierBookingSerializer(booking).data,
        }


class CourierLabelRequestSerializer(serializers.Serializer):
    shipment_id = serializers.UUIDField(required=False)
    tracking_number = serializers.CharField(required=False)

    def validate(self, attrs):
        shipment = None
        if attrs.get("shipment_id"):
            shipment = Shipment.objects.filter(id=attrs["shipment_id"]).first()
        if shipment is None and attrs.get("tracking_number"):
            shipment = Shipment.objects.filter(tracking_number=attrs["tracking_number"]).first()
        if shipment is None:
            raise serializers.ValidationError("Shipment not found.")
        attrs["shipment"] = shipment
        return attrs

    def create(self, validated_data):
        from apps.shipments.services import create_courier_shipment_label

        return create_courier_shipment_label(validated_data["shipment"], actor=self.context["request"].user)


class PickupScheduleCreateSerializer(serializers.Serializer):
    shipment_id = serializers.UUIDField()
    pickup_date = serializers.DateField()
    pickup_slot = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        shipment = Shipment.objects.filter(id=attrs["shipment_id"]).first()
        if not shipment:
            raise serializers.ValidationError({"shipment_id": "Invalid shipment."})
        attrs["shipment"] = shipment
        return attrs

    def create(self, validated_data):
        from apps.shipments.services import schedule_courier_pickup

        return schedule_courier_pickup(
            validated_data["shipment"],
            validated_data["pickup_date"],
            pickup_slot=validated_data.get("pickup_slot", ""),
            actor=self.context["request"].user,
        )


class TrackingSnapshotSerializer(serializers.Serializer):
    shipment_id = serializers.UUIDField(required=False)
    tracking_number = serializers.CharField(required=False)

    def validate(self, attrs):
        shipment = None
        if attrs.get("shipment_id"):
            shipment = Shipment.objects.filter(id=attrs["shipment_id"]).first()
        if shipment is None and attrs.get("tracking_number"):
            shipment = Shipment.objects.filter(tracking_number=attrs["tracking_number"]).first()
        if shipment is None:
            raise serializers.ValidationError("Shipment not found.")
        attrs["shipment"] = shipment
        return attrs

    def create(self, validated_data):
        return generate_courier_tracking_snapshot(validated_data["shipment"])


class WebhookSerializer(serializers.Serializer):
    tracking_number = serializers.CharField(required=False)
    awb_number = serializers.CharField(required=False)
    shipment_id = serializers.CharField(required=False)
    status = serializers.CharField(required=False)
    event_code = serializers.CharField(required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    courier_partner_code = serializers.CharField(required=False, allow_blank=True)
    token = serializers.CharField(required=False, allow_blank=True)


CourierPickupScheduleCreateSerializer = PickupScheduleCreateSerializer

