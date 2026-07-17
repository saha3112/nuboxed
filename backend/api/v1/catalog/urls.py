from django.urls import path

from .views import (
    AdminProductApprovalView,
    AttributeValueListCreateView,
    AdminProductListView,
    BrandDetailView,
    BrandListCreateView,
    CategoryAdminDetailView,
    CategoryAdminListCreateView,
    CategoryReorderView,
    CategoryTreeView,
    ProductAttributeListCreateView,
    PublicProductDetailView,
    RetailerProductDetailView,
    RetailerProductListCreateView,
    RetailerVariantListCreateView,
)

urlpatterns = [
    path("categories/tree/", CategoryTreeView.as_view(), name="catalog-category-tree"),
    path("categories/", CategoryAdminListCreateView.as_view(), name="catalog-category-list"),
    path("categories/<uuid:pk>/", CategoryAdminDetailView.as_view(), name="catalog-category-detail"),
    path("categories/<uuid:category_id>/reorder/", CategoryReorderView.as_view(), name="catalog-category-reorder"),
    path("brands/", BrandListCreateView.as_view(), name="catalog-brand-list"),
    path("brands/<uuid:pk>/", BrandDetailView.as_view(), name="catalog-brand-detail"),
    path("attributes/", ProductAttributeListCreateView.as_view(), name="catalog-attribute-list"),
    path("attribute-options/", AttributeValueListCreateView.as_view(), name="catalog-attribute-option-list"),
    path("retailer/products/", RetailerProductListCreateView.as_view(), name="catalog-retailer-product-list"),
    path("retailer/products/<uuid:product_id>/", RetailerProductDetailView.as_view(), name="catalog-retailer-product-detail"),
    path("retailer/products/<uuid:product_id>/variants/", RetailerVariantListCreateView.as_view(), name="catalog-retailer-variant-list"),
    path("admin/products/", AdminProductListView.as_view(), name="catalog-admin-product-list"),
    path("admin/products/<uuid:product_id>/<str:action>/", AdminProductApprovalView.as_view(), name="catalog-admin-product-approval"),
    path("products/<slug:slug>/", PublicProductDetailView.as_view(), name="catalog-public-product-detail"),
]
