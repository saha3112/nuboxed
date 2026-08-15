from rest_framework import serializers

from apps.catalog.models import Product
from apps.inventory.delivery import (
    estimate_product_delivery,
    normalize_postal_code,
    resolve_geolocation_label,
)
from apps.inventory.models import (
    CategoryDeliveryRule,
    DeliveryLocation,
    LowStockAlert,
    OfflineSale,
    ProductDeliveryRule,
    StockAdjustment,
    StockItem,
    StockLedger,
    Warehouse,
)
from apps.inventory.services import create_offline_sale, manual_stock_adjustment


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = "__all__"


class DeliveryLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryLocation
        fields = "__all__"


class CategoryDeliveryRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoryDeliveryRule
        fields = "__all__"


class ProductDeliveryRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductDeliveryRule
        fields = "__all__"


class StockItemSerializer(serializers.ModelSerializer):
    available_quantity = serializers.IntegerField(read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = StockItem
        fields = "__all__"


class StockLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockLedger
        fields = "__all__"


class StockAdjustmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockAdjustment
        exclude = ("created_by",)

    def create(self, validated_data):
        request = self.context["request"]
        return manual_stock_adjustment(actor=request.user, **validated_data)


class OfflineSaleSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfflineSale
        exclude = ("created_by", "total_amount")

    def create(self, validated_data):
        request = self.context["request"]
        return create_offline_sale(actor=request.user, **validated_data)


class LowStockAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = LowStockAlert
        fields = "__all__"


class DeliveryEstimateSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    pincode = serializers.CharField(required=False, allow_blank=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)

    def validate(self, attrs):
        attrs["pincode"] = normalize_postal_code(attrs.get("pincode", ""))
        if not Product.objects.filter(id=attrs["product_id"]).exists():
            raise serializers.ValidationError({"product_id": "Invalid product."})
        return attrs

    def create(self, validated_data):
        product = Product.objects.select_related("store", "retailer", "category").get(
            id=validated_data["product_id"]
        )
        payload = {
            "pincode": validated_data.get("pincode", ""),
            "latitude": validated_data.get("latitude"),
            "longitude": validated_data.get("longitude"),
            "label": validated_data.get("pincode")
            or resolve_geolocation_label(
                validated_data.get("latitude"),
                validated_data.get("longitude"),
            ),
        }
        estimate = estimate_product_delivery(product, location_payload=payload)
        return {
            "product_id": str(product.id),
            "pincode": payload.get("pincode", ""),
            "location_label": payload.get("label", ""),
            "is_serviceable": estimate["is_serviceable"],
            "is_precise": estimate["is_precise"],
            "date_label": estimate["date_label"],
            "message": estimate["label"],
            "delivery_days": estimate["delivery_days"],
            "handling_days": estimate["handling_days"],
            "warehouse": estimate["warehouse"].name if estimate.get("warehouse") else "",
        }
