from django.urls import path

from .views import (
    RetailerApprovalView,
    RetailerProfileView,
    RetailerRegistrationView,
    RetailerStaffListCreateView,
    RetailerStoreListView,
    RetailerStoreUpdateView,
)

urlpatterns = [
    path("register/", RetailerRegistrationView.as_view(), name="retailer-register"),
    path("profile/", RetailerProfileView.as_view(), name="retailer-profile"),
    path("stores/", RetailerStoreListView.as_view(), name="retailer-stores"),
    path("stores/<uuid:store_id>/", RetailerStoreUpdateView.as_view(), name="retailer-store-update"),
    path("staff/", RetailerStaffListCreateView.as_view(), name="retailer-staff"),
    path("<uuid:retailer_id>/approve/", RetailerApprovalView.as_view(), name="retailer-approve"),
]
