from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.returns_app.views import ReturnRequestViewSet

router = DefaultRouter()
router.register(r"requests", ReturnRequestViewSet, basename="return-request")

urlpatterns = [
    path("", include(router.urls)),
]
