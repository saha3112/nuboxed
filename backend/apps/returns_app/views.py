from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q

from apps.returns_app.models import ReturnRequest
from apps.orders.models import Order
from apps.retailers.models import Retailer
from apps.returns_app.serializers import (
    ReturnRequestSerializer,
    ReturnRequestCreateSerializer,
    ReturnReviewSerializer,
    ReturnPickupScheduleSerializer,
    ReturnQCAssessmentSerializer,
    ReturnRestockDecisionSerializer,
    ReturnRefundApprovalSerializer,
)
from apps.returns_app.services import (
    create_return_request,
    review_return_request,
    schedule_return_pickup,
    complete_return_pickup,
    receive_at_warehouse,
    perform_qc_assessment,
    execute_restock_decision,
    approve_refund_amount,
    process_and_complete_refund,
)
from apps.payments.views import get_user_retailer_ids


class ReturnRequestViewSet(viewsets.ModelViewSet):
    queryset = ReturnRequest.objects.all()
    serializer_class = ReturnRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return ReturnRequest.objects.all()

        retailer_ids = get_user_retailer_ids(user)
        # Customers see their own return requests, Retailers see returns for their sold orders
        return ReturnRequest.objects.filter(
            Q(customer=user) | Q(retailer_id__in=retailer_ids)
        ).distinct()

    def create(self, request, *args, **kwargs):
        """
        Customer files a new return request.
        """
        serializer = ReturnRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        order = get_object_or_404(Order, id=serializer.validated_data["order_id"])

        # Customer check
        if not request.user.is_super_admin and order.customer != request.user:
            return Response({"detail": "Not authorized to file a return for this order."}, status=status.HTTP_403_FORBIDDEN)

        try:
            return_req = create_return_request(
                order=order,
                items_data=serializer.validated_data["items"],
                reason=serializer.validated_data["reason"],
                customer=request.user
            )
            res_serializer = self.get_serializer(return_req)
            return Response(res_serializer.data, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="review")
    def review(self, request, pk=None):
        """
        Retailer/Admin reviews and approves/rejects return request.
        """
        return_req = self.get_object()

        # Retailer check
        if not request.user.is_super_admin:
            retailer_ids = get_user_retailer_ids(request.user)
            if return_req.retailer_id not in retailer_ids:
                return Response({"detail": "Not authorized to review returns for this retailer."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ReturnReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            return_req = review_return_request(
                return_request=return_req,
                approved=serializer.validated_data["approved"],
                notes=serializer.validated_data["notes"],
                reviewer=request.user
            )
            res_serializer = self.get_serializer(return_req)
            return Response(res_serializer.data)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="schedule-pickup")
    def schedule_pickup(self, request, pk=None):
        """
        Retailer schedules carrier pickup.
        """
        return_req = self.get_object()

        # Retailer check
        if not request.user.is_super_admin:
            retailer_ids = get_user_retailer_ids(request.user)
            if return_req.retailer_id not in retailer_ids:
                return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ReturnPickupScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            return_req = schedule_return_pickup(
                return_request=return_req,
                carrier=serializer.validated_data["pickup_carrier"],
                tracking_number=serializer.validated_data["pickup_tracking_number"],
                date=serializer.validated_data["pickup_date"],
                address=serializer.validated_data["pickup_address"],
                actor=request.user
            )
            res_serializer = self.get_serializer(return_req)
            return Response(res_serializer.data)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="complete-pickup")
    def complete_pickup(self, request, pk=None):
        """
        Retailer/Carrier completes return pickup.
        """
        return_req = self.get_object()

        # Retailer check
        if not request.user.is_super_admin:
            retailer_ids = get_user_retailer_ids(request.user)
            if return_req.retailer_id not in retailer_ids:
                return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        try:
            return_req = complete_return_pickup(return_request=return_req, actor=request.user)
            res_serializer = self.get_serializer(return_req)
            return Response(res_serializer.data)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="receive")
    def receive(self, request, pk=None):
        """
        Warehouse receives package, awaiting QC.
        """
        return_req = self.get_object()

        # Retailer check
        if not request.user.is_super_admin:
            retailer_ids = get_user_retailer_ids(request.user)
            if return_req.retailer_id not in retailer_ids:
                return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        try:
            return_req = receive_at_warehouse(return_request=return_req, actor=request.user)
            res_serializer = self.get_serializer(return_req)
            return Response(res_serializer.data)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="qc")
    def qc(self, request, pk=None):
        """
        Warehouse logs QC assessments.
        """
        return_req = self.get_object()

        # Retailer check
        if not request.user.is_super_admin:
            retailer_ids = get_user_retailer_ids(request.user)
            if return_req.retailer_id not in retailer_ids:
                return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ReturnQCAssessmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            return_req = perform_qc_assessment(
                return_request=return_req,
                qc_results=serializer.validated_data["results"],
                actor=request.user
            )
            res_serializer = self.get_serializer(return_req)
            return Response(res_serializer.data)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="restock")
    def restock(self, request, pk=None):
        """
        Warehouse completes restock decision.
        Rule: Stock restores only after QC approval.
        """
        return_req = self.get_object()

        # Retailer check
        if not request.user.is_super_admin:
            retailer_ids = get_user_retailer_ids(request.user)
            if return_req.retailer_id not in retailer_ids:
                return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ReturnRestockDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            return_req = execute_restock_decision(
                return_request=return_req,
                restock_decisions=serializer.validated_data["decisions"],
                actor=request.user
            )
            res_serializer = self.get_serializer(return_req)
            return Response(res_serializer.data)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="approve-refund")
    def approve_refund(self, request, pk=None):
        """
        Retailer approves refund amount (full or partial).
        """
        return_req = self.get_object()

        # Retailer check
        if not request.user.is_super_admin:
            retailer_ids = get_user_retailer_ids(request.user)
            if return_req.retailer_id not in retailer_ids:
                return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ReturnRefundApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            return_req = approve_refund_amount(
                return_request=return_req,
                refund_amount=serializer.validated_data["refund_amount"],
                actor=request.user
            )
            res_serializer = self.get_serializer(return_req)
            return Response(res_serializer.data)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="process-refund")
    def process_refund_action(self, request, pk=None):
        """
        Retailer finishes processing the actual payment refund.
        """
        return_req = self.get_object()

        # Retailer check
        if not request.user.is_super_admin:
            retailer_ids = get_user_retailer_ids(request.user)
            if return_req.retailer_id not in retailer_ids:
                return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        try:
            return_req = process_and_complete_refund(return_request=return_req, actor=request.user)
            res_serializer = self.get_serializer(return_req)
            return Response(res_serializer.data)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
