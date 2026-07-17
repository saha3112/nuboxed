from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok", "service": "commerceos", "version": "v1"})


urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("auth/", include("api.v1.auth.urls")),
    path("catalog/", include("api.v1.catalog.urls")),
    path("inventory/", include("api.v1.inventory.urls")),
    path("shipments/", include("api.v1.shipments.urls")),
    path("retailers/", include("api.v1.retailers.urls")),
    path("payments/", include("apps.payments.urls")),
    path("returns/", include("apps.returns_app.urls")),
    path("marketplace/", include("apps.marketplace.urls")),
    path("schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
]
