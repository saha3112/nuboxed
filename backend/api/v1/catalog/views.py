from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import exceptions
from rest_framework import generics, permissions, response, status
from rest_framework.views import APIView

from apps.catalog.models import (
    AttributeValue,
    Brand,
    Category,
    Product,
    ProductAttribute,
    ProductVariant,
)
from apps.catalog.services import approve_product, reject_product, reorder_category
from apps.rbac.permissions import CommerceAccessPermission

from .serializers import (
    AttributeValueSerializer,
    BrandSerializer,
    CategoryReorderSerializer,
    CategorySerializer,
    ProductApprovalSerializer,
    ProductAttributeSerializer,
    ProductDetailSerializer,
    ProductSerializer,
    ProductVariantSerializer,
    RecursiveCategorySerializer,
)


class CatalogRetailerContextMixin:
    def get_retailer(self):
        membership = (
            self.request.user.account_memberships.select_related("account__retailer_profile")
            .filter(is_active=True, account__retailer_profile__isnull=False)
            .first()
        )
        if not membership:
            raise Http404("Retailer context not found.")
        return membership.account.retailer_profile

    def get_permission_account(self, request):
        try:
            return self.get_retailer().account_id
        except Http404:
            return None


class CategoryTreeView(generics.ListAPIView):
    queryset = Category.objects.filter(parent__isnull=True, is_active=True).order_by("sort_order", "name")
    serializer_class = RecursiveCategorySerializer
    permission_classes = [permissions.AllowAny]


class CategoryAdminListCreateView(generics.ListCreateAPIView):
    queryset = Category.objects.all().order_by("sort_order", "name")
    serializer_class = CategorySerializer
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["catalog.manage"]


class CategoryAdminDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["catalog.manage"]


class CategoryReorderView(APIView):
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["catalog.manage"]

    def post(self, request, category_id):
        category = get_object_or_404(Category, id=category_id)
        serializer = CategoryReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parent = None
        if serializer.validated_data.get("parent_id"):
            parent = get_object_or_404(Category, id=serializer.validated_data["parent_id"])
        category = reorder_category(
            category,
            parent=parent,
            sort_order=serializer.validated_data.get("sort_order", 0),
        )
        return response.Response(CategorySerializer(category).data)


class BrandListCreateView(generics.ListCreateAPIView):
    queryset = Brand.objects.all().order_by("name")
    serializer_class = BrandSerializer
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["catalog.manage"]


class BrandDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["catalog.manage"]


class ProductAttributeListCreateView(generics.ListCreateAPIView):
    queryset = ProductAttribute.objects.all().order_by("name")
    serializer_class = ProductAttributeSerializer
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["catalog.manage"]


class AttributeValueListCreateView(APIView):
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["catalog.manage"]

    def get(self, request):
        queryset = AttributeValue.objects.select_related("attribute").order_by("sort_order", "label")
        attribute_id = request.query_params.get("attribute_id")
        attribute_code = request.query_params.get("attribute_code")
        if attribute_id:
            queryset = queryset.filter(attribute_id=attribute_id)
        if attribute_code:
            queryset = queryset.filter(attribute__code=attribute_code)
        return response.Response(AttributeValueSerializer(queryset, many=True).data)

    def post(self, request):
        attribute = self.get_attribute(request.data)
        items = request.data.get("items")
        if items is None:
            items = [request.data]

        created_objects = []
        for index, item in enumerate(items):
            payload = {
                "attribute": str(attribute.id),
                "label": item.get("label") or item.get("name") or item.get("value"),
                "value": item.get("value") or item.get("label") or item.get("name"),
                "hex_color": item.get("hex_color", ""),
                "sort_order": item.get("sort_order", index),
            }
            serializer = AttributeValueSerializer(data=payload)
            serializer.is_valid(raise_exception=True)
            if attribute.data_type == ProductAttribute.TYPE_COLOR and not serializer.validated_data.get("hex_color"):
                raise exceptions.ValidationError({"hex_color": "Color picker value is required for color options."})
            created_objects.append(serializer.save())

        serializer = AttributeValueSerializer(created_objects, many=True)
        return response.Response(serializer.data, status=status.HTTP_201_CREATED)

    def get_attribute(self, payload):
        attribute_id = payload.get("attribute")
        if attribute_id:
            return get_object_or_404(ProductAttribute, id=attribute_id)

        attribute_code = (payload.get("attribute_code") or "").strip().lower()
        attribute_name = (payload.get("attribute_name") or "Color").strip()
        if attribute_code == "color" or attribute_name.lower() == "color":
            attribute, _ = ProductAttribute.objects.get_or_create(
                code="color",
                defaults={
                    "name": "Color",
                    "data_type": ProductAttribute.TYPE_COLOR,
                    "color_mode": ProductAttribute.COLOR_MODE_MULTI,
                    "is_variant_attribute": True,
                },
            )
            return attribute

        raise exceptions.ValidationError(
            {"attribute": "Provide a valid attribute id or use attribute_code=color for color options."}
        )


class RetailerProductListCreateView(CatalogRetailerContextMixin, generics.ListCreateAPIView):
    serializer_class = ProductSerializer
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["catalog.manage"]

    def get_queryset(self):
        retailer = self.get_retailer()
        queryset = Product.objects.filter(retailer=retailer).select_related("category", "brand", "store")
        store_ids = self.request.user.get_accessible_store_ids(account=retailer.account)
        if store_ids is None:
            return queryset
        return queryset.filter(store_id__in=store_ids)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["retailer"] = self.get_retailer()
        return context

    def perform_create(self, serializer):
        serializer.save(retailer=self.get_retailer())


class RetailerProductDetailView(CatalogRetailerContextMixin, generics.RetrieveUpdateAPIView):
    serializer_class = ProductSerializer
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["catalog.manage"]
    lookup_url_kwarg = "product_id"

    def get_queryset(self):
        retailer = self.get_retailer()
        queryset = Product.objects.filter(retailer=retailer)
        store_ids = self.request.user.get_accessible_store_ids(account=retailer.account)
        if store_ids is None:
            return queryset
        return queryset.filter(store_id__in=store_ids)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["retailer"] = self.get_retailer()
        return context

    def perform_update(self, serializer):
        serializer.save(status=Product.STATUS_PENDING)


class RetailerVariantListCreateView(CatalogRetailerContextMixin, generics.ListCreateAPIView):
    serializer_class = ProductVariantSerializer
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["catalog.manage"]

    def get_product(self):
        return get_object_or_404(self.get_product_queryset(), id=self.kwargs["product_id"])

    def get_product_queryset(self):
        retailer = self.get_retailer()
        queryset = Product.objects.filter(retailer=retailer)
        store_ids = self.request.user.get_accessible_store_ids(account=retailer.account)
        if store_ids is None:
            return queryset
        return queryset.filter(store_id__in=store_ids)

    def get_queryset(self):
        return self.get_product().variants.all()

    def perform_create(self, serializer):
        serializer.save(product=self.get_product())


class AdminProductListView(generics.ListAPIView):
    queryset = Product.objects.select_related("retailer", "store", "category", "brand").all()
    serializer_class = ProductSerializer
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["catalog.manage"]


class AdminProductApprovalView(APIView):
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["catalog.manage"]

    def post(self, request, product_id, action):
        product = get_object_or_404(Product, id=product_id)
        serializer = ProductApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notes = serializer.validated_data.get("approval_notes", "")
        if action == "approve":
            product = approve_product(product, approver=request.user, notes=notes)
        elif action == "reject":
            product = reject_product(product, approver=request.user, notes=notes)
        else:
            return response.Response({"detail": "Invalid approval action."}, status=status.HTTP_400_BAD_REQUEST)
        return response.Response(ProductSerializer(product).data)


class PublicProductDetailView(generics.RetrieveAPIView):
    queryset = Product.objects.filter(status=Product.STATUS_APPROVED, is_active=True).select_related("category", "brand")
    serializer_class = ProductDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"
