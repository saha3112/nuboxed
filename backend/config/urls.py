from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", include("apps.backoffice.urls")),
    path("super-admin/", RedirectView.as_view(url="/admin/", permanent=False)),
    re_path(r"^super-admin/(?P<path>.*)$", RedirectView.as_view(url="/admin/%(path)s", permanent=False)),
    path("", include("apps.storefront.urls")),
    path("", include("apps.catalog.urls")),
    path("", include("apps.inventory.urls")),
    path("retailer/", include("apps.retailers.urls")),
    path("api/v1/", include("api.v1.urls")),
]

# The cPanel Passenger deployment does not always have an Apache alias for
# these directories. Keep the fallback enabled in production as well so a
# missing hosting-level alias cannot render the admin as unstyled HTML.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
