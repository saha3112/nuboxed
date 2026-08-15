from django.http import Http404
from django.db.models import Q
from rest_framework import generics, permissions, status
from rest_framework.response import Response

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
from apps.rbac.permissions import CommerceAccessPermission

from .serializers import (
    CategoryDeliveryRuleSerializer,
    DeliveryEstimateSerializer,
    DeliveryLocationSerializer,
    LowStockAlertSerializer,
    OfflineSaleSerializer,
    ProductDeliveryRuleSerializer,
    StockAdjustmentSerializer,
    StockItemSerializer,
    StockLedgerSerializer,
    WarehouseSerializer,
)


class InventoryRetailerContextMixin:
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

    def get_store_ids(self):
        retailer = self.get_retailer()
        return self.request.user.get_accessible_store_ids(account=retailer.account)


class WarehouseListCreateView(InventoryRetailerContextMixin, generics.ListCreateAPIView):
    serializer_class = WarehouseSerializer
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["inventory.manage"]

    def get_queryset(self):
        retailer = self.get_retailer()
        queryset = Warehouse.objects.filter(retailer=retailer)
        store_ids = self.get_store_ids()
        if store_ids is None:
            return queryset
        return queryset.filter(store_id__in=store_ids) | queryset.filter(store__isnull=True)

    def perform_create(self, serializer):
        serializer.save(retailer=self.get_retailer())


class DeliveryLocationListCreateView(InventoryRetailerContextMixin, generics.ListCreateAPIView):
    serializer_class = DeliveryLocationSerializer
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["inventory.manage"]

    def get_queryset(self):
        retailer = self.get_retailer()
        queryset = DeliveryLocation.objects.filter(retailer=retailer).select_related("store", "warehouse")
        store_ids = self.get_store_ids()
        if store_ids is None:
            return queryset
        return queryset.filter(Q(store_id__in=store_ids) | Q(store__isnull=True))

    def perform_create(self, serializer):
        serializer.save(retailer=self.get_retailer())


class CategoryDeliveryRuleListCreateView(InventoryRetailerContextMixin, generics.ListCreateAPIView):
    serializer_class = CategoryDeliveryRuleSerializer
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["inventory.manage"]

    def get_queryset(self):
        retailer = self.get_retailer()
        queryset = CategoryDeliveryRule.objects.filter(retailer=retailer).select_related("category", "store")
        store_ids = self.get_store_ids()
        if store_ids is None:
            return queryset
        return queryset.filter(Q(store_id__in=store_ids) | Q(store__isnull=True))

    def perform_create(self, serializer):
        serializer.save(retailer=self.get_retailer())


class ProductDeliveryRuleListCreateView(InventoryRetailerContextMixin, generics.ListCreateAPIView):
    serializer_class = ProductDeliveryRuleSerializer
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["inventory.manage"]

    def get_queryset(self):
        retailer = self.get_retailer()
        queryset = ProductDeliveryRule.objects.filter(retailer=retailer).select_related("product", "warehouse")
        store_ids = self.get_store_ids()
        if store_ids is None:
            return queryset
        return queryset.filter(product__store_id__in=store_ids)

    def perform_create(self, serializer):
        serializer.save(retailer=self.get_retailer())


class StockItemListView(InventoryRetailerContextMixin, generics.ListAPIView):
    serializer_class = StockItemSerializer
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["inventory.manage"]

    def get_queryset(self):
        retailer = self.get_retailer()
        queryset = StockItem.objects.filter(product__retailer=retailer).select_related("product", "variant", "warehouse")
        store_ids = self.get_store_ids()
        if store_ids is None:
            return queryset
        return queryset.filter(product__store_id__in=store_ids)


class StockLedgerListView(InventoryRetailerContextMixin, generics.ListAPIView):
    serializer_class = StockLedgerSerializer
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["inventory.manage"]

    def get_queryset(self):
        retailer = self.get_retailer()
        queryset = StockLedger.objects.filter(product__retailer=retailer).select_related("product", "variant", "warehouse")
        store_ids = self.get_store_ids()
        if store_ids is None:
            return queryset
        return queryset.filter(product__store_id__in=store_ids)


class StockAdjustmentCreateView(InventoryRetailerContextMixin, generics.CreateAPIView):
    serializer_class = StockAdjustmentSerializer
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["inventory.manage"]


class OfflineSaleListCreateView(InventoryRetailerContextMixin, generics.ListCreateAPIView):
    serializer_class = OfflineSaleSerializer
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["inventory.manage"]

    def get_queryset(self):
        retailer = self.get_retailer()
        queryset = OfflineSale.objects.filter(product__retailer=retailer).select_related("product", "variant", "warehouse", "store")
        store_ids = self.get_store_ids()
        if store_ids is None:
            return queryset
        return queryset.filter(store_id__in=store_ids)


class LowStockAlertListView(InventoryRetailerContextMixin, generics.ListAPIView):
    serializer_class = LowStockAlertSerializer
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["inventory.manage"]

    def get_queryset(self):
        retailer = self.get_retailer()
        queryset = LowStockAlert.objects.filter(stock_item__product__retailer=retailer, resolved_at__isnull=True)
        store_ids = self.get_store_ids()
        if store_ids is None:
            return queryset
        return queryset.filter(stock_item__product__store_id__in=store_ids)


class DeliveryEstimateView(generics.GenericAPIView):
    serializer_class = DeliveryEstimateSerializer
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.save()
        return Response(payload, status=status.HTTP_200_OK)
