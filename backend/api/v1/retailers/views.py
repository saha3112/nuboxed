from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, response, status
from rest_framework.views import APIView

from apps.retailers.models import Retailer
from apps.retailers.services import approve_retailer
from apps.rbac.permissions import CommerceAccessPermission, IsRetailerAccountMember
from apps.stores.models import Store

from .serializers import (
    RetailerApprovalSerializer,
    RetailerProfileSerializer,
    RetailerRegistrationSerializer,
    RetailerStoreSerializer,
    StoreStaffCreateSerializer,
    StoreStaffSerializer,
    StoreUpdateSerializer,
)


class RetailerRegistrationView(generics.CreateAPIView):
    serializer_class = RetailerRegistrationSerializer
    permission_classes = [permissions.AllowAny]


class RetailerContextMixin:
    def get_retailer(self):
        user = self.request.user
        membership = (
            user.account_memberships.select_related("account__retailer_profile")
            .filter(is_active=True, account__retailer_profile__isnull=False)
            .first()
        )
        if not membership:
            raise Http404("Retailer profile not found.")
        return membership.account.retailer_profile

    def get_permission_account(self, request):
        try:
            return self.get_retailer().account_id
        except Http404:
            return None


class RetailerProfileView(RetailerContextMixin, APIView):
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["stores.manage"]

    def get(self, request):
        retailer = self.get_retailer()
        serializer = RetailerProfileSerializer(retailer, context={"request": request})
        return response.Response(serializer.data)

    def patch(self, request):
        retailer = self.get_retailer()
        serializer = RetailerProfileSerializer(retailer, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response(serializer.data)


class RetailerStoreListView(RetailerContextMixin, generics.ListCreateAPIView):
    serializer_class = StoreUpdateSerializer
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["stores.manage"]

    def get_queryset(self):
        retailer = self.get_retailer()
        store_ids = self.request.user.get_accessible_store_ids(account=retailer.account)
        queryset = retailer.stores.all()
        if store_ids is None:
            return queryset
        return queryset.filter(id__in=store_ids)

    def get_serializer_class(self):
        if self.request.method == "GET":
            return RetailerStoreSerializer
        return StoreUpdateSerializer

    def perform_create(self, serializer):
        retailer = self.get_retailer()
        from apps.retailers.services import unique_slug

        serializer.save(
            retailer=retailer,
            slug=unique_slug(Store, serializer.validated_data["name"]),
            status=Store.STATUS_DRAFT,
        )


class RetailerStoreUpdateView(RetailerContextMixin, generics.RetrieveUpdateAPIView):
    serializer_class = StoreUpdateSerializer
    permission_classes = [CommerceAccessPermission, IsRetailerAccountMember]
    required_permissions = ["stores.manage"]
    lookup_field = "id"
    lookup_url_kwarg = "store_id"

    def get_permission_account(self, request):
        retailer = self.get_retailer()
        return retailer.account_id if retailer else None

    def get_queryset(self):
        retailer = self.get_retailer()
        store_ids = self.request.user.get_accessible_store_ids(account=retailer.account)
        queryset = retailer.stores.all()
        if store_ids is None:
            return queryset
        return queryset.filter(id__in=store_ids)


class RetailerStaffListCreateView(RetailerContextMixin, APIView):
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["staff.manage"]

    def get(self, request):
        retailer = self.get_retailer()
        memberships = retailer.account.memberships.select_related("user", "store").all()
        store_ids = request.user.get_accessible_store_ids(account=retailer.account)
        if store_ids is not None:
            memberships = memberships.filter(store_id__in=store_ids)
        serializer = StoreStaffSerializer(memberships, many=True)
        return response.Response(serializer.data)

    def post(self, request):
        retailer = self.get_retailer()
        serializer = StoreStaffCreateSerializer(data=request.data, context={"retailer": retailer})
        serializer.is_valid(raise_exception=True)
        membership = serializer.save()
        return response.Response(StoreStaffSerializer(membership).data, status=status.HTTP_201_CREATED)


class RetailerApprovalView(APIView):
    permission_classes = [CommerceAccessPermission]
    required_permissions = ["retailers.manage"]

    def post(self, request, retailer_id):
        retailer = get_object_or_404(Retailer, id=retailer_id)
        serializer = RetailerApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        retailer = approve_retailer(
            retailer=retailer,
            approver=request.user,
            notes=serializer.validated_data.get("approval_notes", ""),
        )
        return response.Response(RetailerProfileSerializer(retailer, context={"request": request}).data)
