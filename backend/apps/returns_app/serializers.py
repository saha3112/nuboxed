from rest_framework import serializers
from apps.returns_app.models import ReturnRequest, ReturnItem, ReturnTimeline


class ReturnTimelineSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True)

    class Meta:
        model = ReturnTimeline
        fields = ["id", "status", "title", "note", "actor", "actor_email", "occurred_at"]


class ReturnItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="order_item.product.name", read_only=True)
    product_sku = serializers.CharField(source="order_item.variant.sku", read_only=True, default=None)

    class Meta:
        model = ReturnItem
        fields = ["id", "order_item", "product_name", "product_sku", "quantity", "qc_status", "qc_note", "restock_decision", "restocked_at"]


class ReturnRequestSerializer(serializers.ModelSerializer):
    items = ReturnItemSerializer(many=True, read_only=True)
    timeline_entries = ReturnTimelineSerializer(many=True, read_only=True)
    customer_email = serializers.EmailField(source="customer.email", read_only=True)
    retailer_name = serializers.CharField(source="retailer.legal_name", read_only=True)
    order_number = serializers.CharField(source="order.number", read_only=True)

    class Meta:
        model = ReturnRequest
        fields = [
            "id", "return_number", "order", "order_number", "customer", "customer_email",
            "retailer", "retailer_name", "status", "reason", "rejection_reason",
            "pickup_address", "pickup_date", "pickup_carrier", "pickup_tracking_number",
            "refund_amount", "reviewed_at", "reviewed_by", "items", "timeline_entries",
            "created_at", "updated_at"
        ]
        read_only_fields = ["id", "return_number", "reviewed_at", "reviewed_by", "created_at", "updated_at"]


class ReturnItemInputSerializer(serializers.Serializer):
    order_item_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class ReturnRequestCreateSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    items = ReturnItemInputSerializer(many=True)
    reason = serializers.CharField()


class ReturnReviewSerializer(serializers.Serializer):
    approved = serializers.BooleanField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class ReturnPickupScheduleSerializer(serializers.Serializer):
    pickup_carrier = serializers.CharField(max_length=100)
    pickup_tracking_number = serializers.CharField(max_length=100)
    pickup_date = serializers.DateField()
    pickup_address = serializers.CharField()


class ReturnQCAssessmentItemSerializer(serializers.Serializer):
    return_item_id = serializers.UUIDField()
    qc_status = serializers.ChoiceField(choices=["passed", "failed"])
    qc_note = serializers.CharField(required=False, allow_blank=True, default="")


class ReturnQCAssessmentSerializer(serializers.Serializer):
    results = ReturnQCAssessmentItemSerializer(many=True)


class ReturnRestockItemSerializer(serializers.Serializer):
    return_item_id = serializers.UUIDField()
    restock_decision = serializers.ChoiceField(choices=["restocked", "discarded", "outlet"])


class ReturnRestockDecisionSerializer(serializers.Serializer):
    decisions = ReturnRestockItemSerializer(many=True)


class ReturnRefundApprovalSerializer(serializers.Serializer):
    refund_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0.00)
