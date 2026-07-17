from rest_framework import serializers

from apps.catalog.models import (
    AttributeValue,
    Brand,
    Category,
    Product,
    ProductAttribute,
    ProductMedia,
    ProductVariant,
)
from apps.catalog.services import unique_slug, unique_sku


class RecursiveCategorySerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "sort_order",
            "is_featured",
            "seo_title",
            "seo_description",
            "children",
        )

    def get_children(self, obj):
        return RecursiveCategorySerializer(
            obj.children.filter(is_active=True).order_by("sort_order", "name"),
            many=True,
        ).data


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = "__all__"
        read_only_fields = ("slug", "created_at", "updated_at")

    def create(self, validated_data):
        validated_data["slug"] = unique_slug(Category, validated_data["name"])
        return super().create(validated_data)


class CategoryReorderSerializer(serializers.Serializer):
    parent_id = serializers.UUIDField(required=False, allow_null=True)
    sort_order = serializers.IntegerField(required=False, default=0)


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = "__all__"
        read_only_fields = ("slug", "created_at", "updated_at")

    def create(self, validated_data):
        validated_data["slug"] = unique_slug(Brand, validated_data["name"])
        return super().create(validated_data)


class AttributeValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttributeValue
        fields = "__all__"


class ProductAttributeSerializer(serializers.ModelSerializer):
    values = AttributeValueSerializer(many=True, read_only=True)

    class Meta:
        model = ProductAttribute
        fields = "__all__"


class ProductMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductMedia
        fields = "__all__"


class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = "__all__"
        read_only_fields = ("sku",)

    def create(self, validated_data):
        if not validated_data.get("sku"):
            validated_data["sku"] = unique_sku(ProductVariant, validated_data["name"])
        return super().create(validated_data)


class ProductSerializer(serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True, read_only=True)
    assets = ProductMediaSerializer(many=True, read_only=True, source="media_items")

    class Meta:
        model = Product
        fields = "__all__"
        read_only_fields = (
            "slug",
            "sku",
            "status",
            "approved_at",
            "approved_by",
            "approval_notes",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        retailer = self.context.get("retailer")
        store = attrs.get("store") or getattr(self.instance, "store", None)
        if retailer and store and store.retailer_id != retailer.id:
            raise serializers.ValidationError("Invalid store for this retailer.")
        return attrs

    def create(self, validated_data):
        validated_data["slug"] = unique_slug(Product, validated_data["name"])
        validated_data["sku"] = unique_sku(Product, validated_data["name"])
        validated_data.setdefault("status", Product.STATUS_PENDING)
        return super().create(validated_data)


class ProductApprovalSerializer(serializers.Serializer):
    approval_notes = serializers.CharField(required=False, allow_blank=True)


class ProductDetailSerializer(serializers.ModelSerializer):
    category = RecursiveCategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    assets = ProductMediaSerializer(many=True, read_only=True, source="media_items")
    variants = ProductVariantSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = "__all__"
