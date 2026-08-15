from django.urls import path

from .views import (
    AdminProductApproveActionView,
    ProductDetailPageView,
    RetailerCatalogDashboardView,
    RetailerProductCreateView,
    RetailerProductEditView,
    RetailerProductBulkActionView,
    RetailerProductVariantCreateView,
    RetailerProductVariantEditView,
    MediaLibraryListView,
    MediaLibraryUploadView,
    RetailerProductVariantGenerateView,
    RetailerProductMergeView,
    RetailerProductVariantListView,
    RetailerProductVariantDeleteView,
    ProductReviewSubmitView,
    RetailerProductReviewListView,
    RetailerProductReviewStatusView,
)

app_name = "catalog"

urlpatterns = [
    path("retailer/catalog/products/", RetailerCatalogDashboardView.as_view(), name="retailer-products"),
    path("retailer/catalog/products/bulk-action/", RetailerProductBulkActionView.as_view(), name="retailer-products-bulk-action"),
    path("retailer/catalog/reviews/", RetailerProductReviewListView.as_view(), name="retailer-reviews"),
    path("retailer/catalog/reviews/<uuid:pk>/<str:action>/", RetailerProductReviewStatusView.as_view(), name="retailer-review-action"),
    path("retailer/catalog/variants/", RetailerProductVariantListView.as_view(), name="retailer-variants"),
    path("retailer/catalog/products/new/", RetailerProductCreateView.as_view(), name="retailer-product-create"),
    path("retailer/catalog/products/<uuid:pk>/edit/", RetailerProductEditView.as_view(), name="retailer-product-edit"),
    path("retailer/catalog/products/<uuid:product_id>/variants/new/", RetailerProductVariantCreateView.as_view(), name="retailer-product-variant-create"),
    path("retailer/catalog/variants/<uuid:variant_id>/edit/", RetailerProductVariantEditView.as_view(), name="retailer-product-variant-edit"),
    path("retailer/catalog/variants/<uuid:variant_id>/delete/", RetailerProductVariantDeleteView.as_view(), name="retailer-product-variant-delete"),
    path("products/<slug:slug>/", ProductDetailPageView.as_view(), name="product-detail"),
    path("products/<uuid:product_id>/reviews/submit/", ProductReviewSubmitView.as_view(), name="product-review-submit"),
    path("super-admin/products/<uuid:pk>/<str:action>/", AdminProductApproveActionView.as_view(), name="admin-approve"),
    path("api/media-library/", MediaLibraryListView.as_view(), name="api-media-library-list"),
    path("api/media-library/upload/", MediaLibraryUploadView.as_view(), name="api-media-library-upload"),
    path("api/products/<uuid:product_id>/generate-variants/", RetailerProductVariantGenerateView.as_view(), name="api-generate-variants"),
    path("api/products/<uuid:product_id>/merge-product/", RetailerProductMergeView.as_view(), name="api-merge-product"),
]
