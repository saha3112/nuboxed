import csv
import json
from datetime import datetime, timedelta
from urllib.parse import urlencode

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Case, F, IntegerField, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.forms import modelform_factory, modelformset_factory
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.generic import CreateView, FormView, TemplateView, UpdateView, View

from apps.backoffice.forms import (
    BackofficeAttributeOptionsForm,
    BackofficeCategoryForm,
    BackofficeLoginForm,
    SuperAdminSecurityForm,
    AmazonRetailerMenuSettingsForm,
    BackofficeProductForm,
    BackofficeProductAttributeForm,
    BackofficePermissionForm,
    BackofficeRetailerCreateForm,
    BackofficeRetailerUpdateForm,
    BackofficeStoreForm,
    BackofficeSliderForm,
    BackofficeBrandSettingsForm,
    HomePageSettingsForm, HomeTrustCardFormSet, HomeReviewCardFormSet,
    BackofficeUserCreateForm,
    BackofficeUserUpdateForm,
    EmailSettingsForm,
    CourierPartnerForm,
    WarehouseForm,
    AmazonConnectionForm, MASKED_SECRET_VALUE,
    SellerVerificationPageSettingForm, SellerVerificationDocumentSettingForm,
    SellerVerificationDocumentCreateForm,
    RetailerRegistrationFieldForm,
)
from apps.backoffice.registry import MODULES, grouped_modules
from apps.catalog.models import (
    AttributeValue, ProductAttribute, Product, ProductVariantAttributeValue, Brand,
    PhonePlatform, PhoneBrand, PhoneModel, PhoneModelVariant,
    PhoneStorageOption, PhoneColorOption, PhoneRamOption,
)
from apps.catalog.services import normalize_comma_separated_phone_models, split_comma_values, sync_split_phone_models_from_combined
from apps.catalog.device_presets import seed_device_catalog, rebuild_device_options_and_variants
from apps.rbac.constants import ROLE_SUPER_ADMIN
from apps.users.models import User
from apps.notifications.models import Notification
from apps.inventory.models import LowStockAlert, StockItem, Warehouse, OfflineSale
from apps.inventory.forms import OfflineSaleForm
from apps.inventory.services import canonical_stock_items, offline_sales_enabled, set_offline_sales_enabled, set_offline_sale_active
from apps.retailers.models import Retailer, SellerVerificationDocumentSetting, SellerVerificationPageSetting, RetailerRegistrationFieldSetting
from apps.stores.models import Store, StoreRating
from apps.orders.models import Coupon, Order
from apps.orders.forms import OrderStatusForm, OrderWorkflowGlobalSettingForm, OrderWorkflowStoreOverrideForm, OrderWorkflowSettingForm, EmailTemplateForm
from apps.orders.services import coupon_feature_enabled, update_order_status, generate_delivery_label, get_order_workflow_setting, build_order_timeline
from apps.orders.models import OrderWorkflowGlobalSetting, OrderWorkflowStoreOverride, OrderWorkflowSetting
from apps.payments.models import Invoice, PaymentTransaction
from apps.payments.services import process_refund, amount_in_words
from decimal import Decimal, InvalidOperation
from apps.payments.services import generate_invoice_for_order
from apps.settings_app.models import Setting
from apps.settings_app.models import BrandSettings
from apps.notifications.models import NotificationTemplate
from apps.notifications.services import ensure_order_email_templates
from apps.notifications.services import send_test_email
from apps.common.security import build_public_url
from apps.cms.models import HomePageSettings, HomeReviewCard, HomeTrustCard, Page
from apps.marketplace.models import MarketplaceConnector, MarketplaceConnection, MarketplaceListing, MarketplaceStoreMapping, MarketplaceSyncJob, AmazonOrderTracking, MarketplaceSetting
from apps.marketplace.drivers.providers import get_driver
from apps.common.encryption import encrypt, decrypt
from apps.common.captcha import verify_captcha, get_captcha_settings, DEFAULTS as CAPTCHA_DEFAULTS


def sync_device_brand_to_catalog_brand(phone_brand, previous_name=""):
    """Expose Device Models brands in the regular Catalog > Brands module."""
    name = (phone_brand.name or "").strip()
    if not name:
        return None
    catalog_brand = None
    if previous_name:
        catalog_brand = Brand.objects.filter(name__iexact=previous_name).order_by("created_at").first()
    if not catalog_brand:
        catalog_brand = Brand.objects.filter(name__iexact=name).order_by("created_at").first()
    if catalog_brand is None:
        base_slug = slugify(name) or "brand"
        brand_slug = base_slug
        counter = 1
        while Brand.objects.filter(slug=brand_slug).exists():
            brand_slug = f"{base_slug}-{counter}"
            counter += 1
        return Brand.objects.create(name=name, slug=brand_slug, is_active=phone_brand.is_active)
    changed = []
    if catalog_brand.name != name:
        catalog_brand.name = name
        changed.append("name")
    if catalog_brand.is_active != phone_brand.is_active:
        catalog_brand.is_active = phone_brand.is_active
        changed.append("is_active")
    if changed:
        catalog_brand.save(update_fields=[*changed, "updated_at"])
    return catalog_brand
from apps.marketplace.services import enqueue_sync_job, process_sync_job, sync_product_amazon_mapping


class AmazonIntegrationView(LoginRequiredMixin, UserPassesTestMixin, View):
    login_url = reverse_lazy("backoffice:login")
    session_user_key = "backoffice_user_id"

    def dispatch(self, request, *args, **kwargs):
        user_id = request.session.get(self.session_user_key)
        self.portal_user = User.objects.filter(pk=user_id, is_active=True).first() if user_id else None
        if self.portal_user:
            request.user = self.portal_user
        return super().dispatch(request, *args, **kwargs)

    def test_func(self):
        user = getattr(self, "portal_user", None)
        return bool(user) and user.is_authenticated and (user.is_superuser or user.global_roles.filter(role__code=ROLE_SUPER_ADMIN, account_membership__isnull=True).exists())

    def handle_no_permission(self):
        return redirect(self.login_url)
    template_name = "backoffice/amazon_integration.html"
    AMAZON_ENDPOINTS = {
        "sandbox": {"na": "https://sandbox.sellingpartnerapi-na.amazon.com", "eu": "https://sandbox.sellingpartnerapi-eu.amazon.com", "fe": "https://sandbox.sellingpartnerapi-fe.amazon.com"},
        "production": {"na": "https://sellingpartnerapi-na.amazon.com", "eu": "https://sellingpartnerapi-eu.amazon.com", "fe": "https://sellingpartnerapi-fe.amazon.com"},
    }

    def _amazon_endpoint(self, environment, region):
        return self.AMAZON_ENDPOINTS.get(environment, self.AMAZON_ENDPOINTS["sandbox"]).get(region, self.AMAZON_ENDPOINTS["sandbox"]["eu"])

    def _amazon_mode_credentials(self, credentials, environment):
        """Return the selected mode's credentials, with legacy fallback.

        Older connections stored one shared credential set.  Keeping the
        fallback here lets those connections continue to work while every
        subsequent save creates an independent sandbox/production profile.
        """
        credentials = credentials or {}
        profile = credentials.get(environment)
        if isinstance(profile, dict):
            return dict(profile)
        # Once either explicit profile exists, a missing mode is intentionally
        # blank rather than inheriting the other mode's credentials.
        if any(isinstance(credentials.get(name), dict) for name in ("sandbox", "production")):
            return {}
        return dict(credentials)

    def _amazon_mode_profiles(self, credentials):
        """Build safe, browser-readable mode profiles (never expose secrets)."""
        profiles = {}
        for environment in ("sandbox", "production"):
            profile = self._amazon_mode_credentials(credentials, environment)
            regions = profile.get("regions") or [profile.get("region", "eu")]
            marketplaces = profile.get("marketplace_ids") or [profile.get("marketplace_id", "A1PA6795UKMFR9")]
            token_key = "live_refresh_token" if environment == "production" else "sandbox_refresh_token"
            token_exists = bool(profile.get(token_key) or (environment == "sandbox" and profile.get("refresh_token")))
            profiles[environment] = {
                "application_name": profile.get("application_name", ""),
                "application_id": profile.get("application_id", ""),
                "client_identifier": profile.get("client_identifier", profile.get("client_id", "")),
                "client_secret": MASKED_SECRET_VALUE if profile.get("client_secret") else "",
                "refresh_token": MASKED_SECRET_VALUE if token_exists else "",
                "endpoint": profile.get("endpoint", self._amazon_endpoint(environment, profile.get("region", regions[0]))),
                "seller_id": profile.get("seller_id", ""),
                "region_mode": profile.get("region_mode", "single" if len(regions) == 1 else "multiple"),
                "region": profile.get("region", regions[0]),
                "regions": regions,
                "marketplace_mode": profile.get("marketplace_mode", "single" if len(marketplaces) == 1 else "multiple"),
                "marketplace_id": profile.get("marketplace_id", marketplaces[0]),
                "marketplace_ids": marketplaces,
                "aws_access_key_id": profile.get("aws_access_key_id", ""),
                "aws_secret_access_key": MASKED_SECRET_VALUE if profile.get("aws_secret_access_key") else "",
                "auto_sync": profile.get("auto_sync", True),
            }
        return profiles

    def _connection(self):
        connector = MarketplaceConnector.objects.filter(code="amazon").first()
        return MarketplaceConnection.objects.filter(connector=connector).select_related("retailer", "store").order_by("retailer_id", "-created_at").first() if connector else None

    def _production_token_monitor(self, connection):
        profile = ((connection.credentials or {}).get("production") or {}) if connection else {}
        refreshed_at = parse_datetime(profile.get("token_refreshed_at", "")) if profile.get("token_refreshed_at") else None
        if refreshed_at and timezone.is_naive(refreshed_at):
            refreshed_at = timezone.make_aware(refreshed_at, timezone.get_current_timezone())
        next_refresh_at = refreshed_at + timedelta(minutes=55) if refreshed_at else None
        now = timezone.now()
        if not profile.get("live_refresh_token"):
            state = "missing"
            label = "Production token not configured"
        elif profile.get("last_refresh_result") == "failed":
            state = "error"
            label = "Last production refresh failed"
        elif not refreshed_at:
            state = "pending"
            label = "Waiting for first automatic access-token refresh"
        elif next_refresh_at and next_refresh_at <= now:
            state = "due"
            label = "Refresh due"
        else:
            state = "healthy"
            label = "Auto-refresh active"
        continuity = profile.get("refresh_token_continuity")
        continuity_label = {
            "unchanged": "Amazon returned the same refresh token",
            "rotated": "Amazon rotated the refresh token and it was saved",
        }.get(continuity, "Not verified yet")
        return {
            "state": state,
            "label": label,
            "last_refresh_at": refreshed_at,
            "next_refresh_at": next_refresh_at,
            "fingerprint": profile.get("refresh_token_fingerprint") or "—",
            "continuity": continuity_label,
            "continuity_label": continuity_label,
            "last_error": profile.get("last_refresh_error", ""),
        }

    def _context(self, form=None, notice="", notice_type=""):
        connection = self._connection()
        listings = MarketplaceListing.objects.filter(connection=connection).select_related("product", "fulfillment_location") if connection else MarketplaceListing.objects.none()
        store_mappings = MarketplaceStoreMapping.objects.filter(connection=connection).select_related("store", "warehouse") if connection else MarketplaceStoreMapping.objects.none()
        if connection:
            job_rows = MarketplaceSyncJob.objects.filter(connection=connection).order_by("-created_at")
            latest_jobs, seen_flows = [], set()
            for job in job_rows:
                flow = (job.job_type, job.direction)
                if flow in seen_flows:
                    continue
                latest_jobs.append(job)
                seen_flows.add(flow)
                if len(latest_jobs) >= 8:
                    break
            jobs = latest_jobs
        else:
            jobs = []
        # A newer pending job has an empty result. Use the latest completed
        # import for the monitor counters so a queued retry cannot reset a
        # previously verified Amazon catalog to zero.
        latest_product_import = MarketplaceSyncJob.objects.filter(connection=connection, job_type=MarketplaceSyncJob.TYPE_PRODUCT_SYNC, direction=MarketplaceSyncJob.DIRECTION_INBOUND, status=MarketplaceSyncJob.STATUS_COMPLETED).order_by("-created_at").first() if connection else None
        saved_credentials = connection.credentials if connection else {}
        production_profile = saved_credentials.get("production") if isinstance(saved_credentials.get("production"), dict) else {}
        production_token_refreshed_at = production_profile.get("token_refreshed_at")
        sync_ready = bool(saved_credentials.get("seller_id") and saved_credentials.get("marketplace_id") and saved_credentials.get("refresh_token") and saved_credentials.get("regions", [saved_credentials.get("region", "eu")]))
        health_score = 0
        health_label = "Not connected"
        health_tone = "neutral"
        health_components = []
        if connection:
            latest_job = jobs[0] if jobs else None
            recent_sync = bool(connection.last_sync_at and connection.last_sync_at >= timezone.now() - timedelta(hours=24))
            mapped_count = listings.count()
            store_count = store_mappings.count()
            health_components = [
                {"label": "LWA authentication", "status": "ok" if connection.status == MarketplaceConnection.STATUS_ACTIVE else "error", "detail": "Amazon token is valid" if connection.status == MarketplaceConnection.STATUS_ACTIVE else (connection.error_message or "Authentication needs attention")},
                {"label": "SP-API endpoint", "status": "ok" if saved_credentials.get("endpoint") else "error", "detail": "European sandbox endpoint configured" if saved_credentials.get("endpoint") else "Endpoint is missing"},
                {"label": "Seller & marketplace access", "status": "ok" if sync_ready else "warning", "detail": "Product, stock and order sync ready for the selected country" if sync_ready else "Seller ID, marketplace or selected refresh token is missing"},
                {"label": "Retailer store mapping", "status": "ok" if store_count else "warning", "detail": f"{store_count} store{'s' if store_count != 1 else ''} connected automatically" if store_count else "Save settings to map active stores"},
                {"label": "Sync heartbeat", "status": "ok" if recent_sync else "warning", "detail": f"Last successful sync {connection.last_sync_at:%d %b %Y, %H:%M}" if recent_sync else ("Waiting for the first sync" if not latest_job else f"Latest job: {latest_job.get_status_display()}")},
            ]
            health_score = (45 if connection.status == MarketplaceConnection.STATUS_ACTIVE else 15) + (15 if saved_credentials.get("endpoint") else 0) + (20 if sync_ready else 0) + (10 if store_count else 0) + (10 if recent_sync else 0)
            if connection.status == MarketplaceConnection.STATUS_ERROR:
                health_label, health_tone = "Action required", "error"
            elif health_score >= 85:
                health_label, health_tone = "Healthy", "ok"
            elif health_score >= 60:
                health_label, health_tone = "Connected · setup incomplete", "warning"
            else:
                health_label, health_tone = "Needs attention", "error"
        menu_setting = MarketplaceSetting.objects.filter(key="amazon_retailer_menu_enabled").first()
        return {"form": form or AmazonConnectionForm(), "connection": connection, "listings": listings, "store_mappings": store_mappings, "jobs": jobs, "latest_product_import": latest_product_import, "production_token_refreshed_at": production_token_refreshed_at, "production_token_monitor": self._production_token_monitor(connection), "sync_ready": sync_ready, "health_score": health_score, "health_label": health_label, "health_tone": health_tone, "health_components": health_components, "amazon_retailer_menu_enabled": (menu_setting.value or {}).get("enabled", False) if menu_setting else False, "notice": notice, "notice_type": notice_type, "page_title": "Amazon SP-API", "active_group": "Amazon SP-API", "sidebar_groups": grouped_modules()}

    def get(self, request):
        if request.GET.get("snapshot") == "1":
            snapshot = self._context()
            latest_import = snapshot.get("latest_product_import")
            result = (latest_import.result or {}) if latest_import else {}
            jobs = snapshot["jobs"]
            listings = snapshot["listings"]
            return JsonResponse({
                "ok": True,
                "connection_status": snapshot["connection"].status if snapshot["connection"] else "inactive",
                "production_token_monitor": snapshot["production_token_monitor"],
                "import": {
                    "status": latest_import.status if latest_import else "not_run",
                    "imported_count": result.get("imported_count", 0),
                    "matched_count": result.get("matched_count", 0),
                    "unmatched_count": result.get("unmatched_count", 0),
                    "created_at": latest_import.created_at.isoformat() if latest_import else None,
                },
                "jobs": [{"type": job.get_job_type_display(), "direction": job.direction, "direction_label": "Amazon → Nuboxed" if job.direction == MarketplaceSyncJob.DIRECTION_INBOUND else "Nuboxed → Amazon", "status": job.status, "created_at": job.created_at.isoformat() if job.created_at else None, "updated_at": job.updated_at.isoformat() if job.updated_at else None} for job in jobs],
                "listings": [{"sku": item.seller_sku, "product": item.product.name, "store": item.product.store.name, "warehouse": item.fulfillment_location.name if item.fulfillment_location else "Auto / retailer stock", "status": item.status, "last_pushed": item.last_pushed_at.isoformat() if item.last_pushed_at else "—"} for item in listings[:50]],
            })
        if request.GET.get("health") == "1":
            snapshot = self._context()
            connection = snapshot["connection"]
            return JsonResponse({
                "ok": True,
                "score": snapshot["health_score"],
                "label": snapshot["health_label"],
                "tone": snapshot["health_tone"],
                "components": snapshot["health_components"],
                "status": connection.status if connection else "inactive",
                "last_sync": connection.last_sync_at.isoformat() if connection and connection.last_sync_at else None,
                "production_token_refreshed_at": snapshot.get("production_token_refreshed_at"),
                "server_time": timezone.now().isoformat(),
            })
        connection = self._connection()
        initial = {}
        if connection:
            c = connection.credentials or {}
            environment = c.get("environment", "sandbox")
            active = self._amazon_mode_credentials(c, environment)
            saved_regions = active.get("regions") or [active.get("region", "eu")]
            saved_marketplaces = active.get("marketplace_ids") or [active.get("marketplace_id", "A1PA6795UKMFR9")]
            initial = {"environment": environment, "region_mode": active.get("region_mode", "single" if len(saved_regions) == 1 else "multiple"), "region": active.get("region", saved_regions[0]), "regions": saved_regions, "application_name": active.get("application_name", connection.name), "application_id": active.get("application_id", ""), "client_identifier": active.get("client_identifier", active.get("client_id", "")), "client_secret": MASKED_SECRET_VALUE if active.get("client_secret") else "", "sandbox_refresh_token": MASKED_SECRET_VALUE if self._amazon_mode_credentials(c, "sandbox").get("sandbox_refresh_token", self._amazon_mode_credentials(c, "sandbox").get("refresh_token")) else "", "live_refresh_token": MASKED_SECRET_VALUE if self._amazon_mode_credentials(c, "production").get("live_refresh_token") else "", "endpoint": active.get("endpoint", self._amazon_endpoint(environment, active.get("region", saved_regions[0]))), "seller_id": active.get("seller_id", ""), "marketplace_id": active.get("marketplace_id", saved_marketplaces[0]), "marketplace_mode": active.get("marketplace_mode", "single" if len(saved_marketplaces) == 1 else "multiple"), "marketplace_ids": saved_marketplaces, "aws_access_key_id": active.get("aws_access_key_id", ""), "aws_secret_access_key": MASKED_SECRET_VALUE if active.get("aws_secret_access_key") else "", "auto_sync": active.get("auto_sync", True)}
        context = self._context(AmazonConnectionForm(initial=initial))
        context["amazon_mode_profiles"] = self._amazon_mode_profiles(connection.credentials if connection else {})
        return render(request, self.template_name, context)

    def post(self, request):
        action = request.POST.get("action", "save")
        ajax = request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("accept", "")
        connection = self._connection()
        if action == "test" and connection:
            try:
                result = get_driver(connection).refresh_token()
                if ajax:
                    return JsonResponse({"ok": True, "message": "Amazon connection verified successfully.", "status": connection.status})
                messages.success(request, "Amazon connection verified successfully.")
                return redirect("backoffice:amazon-integration")
            except Exception as exc:
                connection.status = MarketplaceConnection.STATUS_ERROR
                connection.error_message = str(exc)
                connection.save(update_fields=["status", "error_message", "updated_at"])
                if ajax:
                    return JsonResponse({"ok": False, "message": str(exc), "status": connection.status}, status=400)
                messages.error(request, str(exc))
                return redirect("backoffice:amazon-integration")
        if action == "sync" and connection:
            queued = []
            sync_plan = (
                (MarketplaceSyncJob.TYPE_PRODUCT_SYNC, MarketplaceSyncJob.DIRECTION_INBOUND, {}),
                (MarketplaceSyncJob.TYPE_ORDER_IMPORT, MarketplaceSyncJob.DIRECTION_INBOUND, {}),
                (MarketplaceSyncJob.TYPE_STOCK_SYNC, MarketplaceSyncJob.DIRECTION_INBOUND, {"from_product_import": True}),
                (MarketplaceSyncJob.TYPE_PRODUCT_SYNC, MarketplaceSyncJob.DIRECTION_OUTBOUND, {}),
                (MarketplaceSyncJob.TYPE_STOCK_SYNC, MarketplaceSyncJob.DIRECTION_OUTBOUND, {}),
            )
            for job_type, direction, payload in sync_plan:
                job = enqueue_sync_job(connection, job_type, direction, payload)
                # If this is an older pending row, enqueue_sync_job correctly
                # deduplicates it. In the local no-worker profile, execute it
                # here so Sync Now cannot leave a stale pending state.
                if job.status == MarketplaceSyncJob.STATUS_PENDING:
                    process_sync_job(job)
                queued.append(str(job.id))
            if ajax:
                return JsonResponse({"ok": True, "message": "Amazon products, orders and stock were reconciled. Matched quantities were pushed back to Amazon.", "status": connection.status, "job_ids": queued})
            messages.success(request, "Product, stock and order sync jobs were started. Review the job status below.")
            return redirect("backoffice:amazon-integration")
        form = AmazonConnectionForm(request.POST)
        if not form.is_valid():
            if ajax:
                return JsonResponse({"ok": False, "message": "Please correct the highlighted fields.", "errors": form.errors.get_json_data()}, status=400)
            return render(request, self.template_name, self._context(form))
        data = form.cleaned_data
        connector, _ = MarketplaceConnector.objects.update_or_create(code="amazon", defaults={"name": "Amazon Selling Partner API", "connector_type": "amazon", "status": "active"})
        environment = data["environment"]
        region = data["region"]
        regions = list(data.get("regions") or [region])
        marketplace_ids = list(data.get("marketplace_ids") or [data["marketplace_id"]])
        existing = connection.credentials if connection else {}
        # Each mode owns its complete configuration.  The top-level values
        # remain as a compatibility mirror for older marketplace services.
        mode_profile = self._amazon_mode_credentials(existing, environment)
        has_mode_profiles = any(isinstance(existing.get(name), dict) for name in ("sandbox", "production"))
        mode_profile.update({"environment": environment, "region_mode": data["region_mode"], "region": region, "regions": regions, "region_profiles": {code: {"endpoint": self._amazon_endpoint(environment, code)} for code in regions}, "marketplace_mode": data["marketplace_mode"], "marketplace_id": data["marketplace_id"], "marketplace_ids": marketplace_ids, "marketplace_profiles": {marketplace_id: {"region": AmazonConnectionForm.MARKETPLACES[marketplace_id][1], "marketplace_id": marketplace_id} for marketplace_id in marketplace_ids if marketplace_id in AmazonConnectionForm.MARKETPLACES}, "application_name": data["application_name"], "application_id": data["application_id"], "client_identifier": data["client_identifier"], "endpoint": self._amazon_endpoint(environment, region), "seller_id": data["seller_id"], "auto_sync": data["auto_sync"]})
        secret_keys = (("client_secret", "client_secret"), ("sandbox_refresh_token", "sandbox_refresh_token"), ("live_refresh_token", "live_refresh_token"), ("aws_secret_access_key", "aws_secret_access_key"))
        for key, stored_key in secret_keys:
            old_value = mode_profile.get(stored_key) or (existing.get(stored_key) if not has_mode_profiles else None)
            if key == "sandbox_refresh_token" and not has_mode_profiles:
                old_value = old_value or existing.get("refresh_token")
            if data.get(key) and data[key] != MASKED_SECRET_VALUE:
                mode_profile[stored_key] = encrypt(data[key])
            elif old_value:
                mode_profile[stored_key] = old_value
        # A new production secret or refresh token starts a fresh verification
        # cycle; do not keep displaying an error generated by the old pair.
        if environment == "production" and (
            data.get("client_secret") not in (None, "", MASKED_SECRET_VALUE)
            or data.get("live_refresh_token") not in (None, "", MASKED_SECRET_VALUE)
        ):
            for key in ("token_refreshed_at", "refresh_token_fingerprint", "refresh_token_continuity", "last_refresh_failed_at"):
                mode_profile.pop(key, None)
            mode_profile["last_refresh_result"] = "pending"
            mode_profile["last_refresh_error"] = ""
        mode_profile["aws_access_key_id"] = data.get("aws_access_key_id") or mode_profile.get("aws_access_key_id", "")
        credentials = dict(existing)
        credentials[environment] = mode_profile
        credentials.update(mode_profile)
        # Keep both token names available in the compatibility mirror.
        for profile_name, token_name in (("sandbox", "sandbox_refresh_token"), ("production", "live_refresh_token")):
            saved_profile = credentials.get(profile_name) or {}
            if saved_profile.get(token_name):
                credentials[token_name] = saved_profile[token_name]
        active_token = mode_profile.get("live_refresh_token") if environment == "production" else mode_profile.get("sandbox_refresh_token")
        if active_token: credentials["refresh_token"] = active_token
        credentials["client_id"] = data["client_identifier"]
        # One Amazon seller connection belongs to the retailer. Stores below
        # that retailer are tracked separately through store mappings.
        connection = MarketplaceConnection.objects.filter(connector=connector).order_by("retailer_id", "-created_at").first()
        if connection is None:
            connection = MarketplaceConnection(connector=connector)
        connection.retailer = None
        connection.store = None
        connection.name = data["application_name"]
        connection.credentials = credentials
        connection.status = MarketplaceConnection.STATUS_INACTIVE
        connection.save()
        for store in Store.objects.filter(is_active=True):
            warehouse = Warehouse.objects.filter(retailer=store.retailer, store=store, is_active=True).order_by("-is_default", "name").first()
            MarketplaceStoreMapping.objects.update_or_create(connection=connection, store=store, defaults={"warehouse": warehouse, "amazon_store_code": store.slug, "is_enabled": True, "error_message": ""})
        products = Product.objects.all()
        for product in products.filter(is_active=True):
            mapping = MarketplaceStoreMapping.objects.filter(connection=connection, store=product.store, is_enabled=True).select_related("warehouse").first()
            MarketplaceListing.objects.update_or_create(connection=connection, product=product, variant=None, defaults={"seller_sku": product.sku, "marketplace_id": data["marketplace_id"], "fulfillment_location": mapping.warehouse if mapping else None})
            for variant in product.variants.filter(deleted_at__isnull=True):
                MarketplaceListing.objects.update_or_create(connection=connection, product=product, variant=variant, defaults={"seller_sku": variant.sku, "marketplace_id": data["marketplace_id"], "fulfillment_location": mapping.warehouse if mapping else None})
        # Saving validates LWA immediately, while product/order sync remains a
        # separate action because Amazon also needs Seller ID and AWS signing.
        save_message = "Amazon settings were saved, but the connection test failed."
        save_ok = False
        try:
            get_driver(connection).refresh_token()
            save_ok = True
            save_message = "Amazon settings saved. LWA connection is active and all retailer stores/SKUs are mapped."
            messages.success(request, "Amazon settings saved. LWA connection is active and all retailer stores/SKUs are mapped.")
        except Exception as exc:
            connection.status = MarketplaceConnection.STATUS_ERROR
            connection.error_message = str(exc)
            connection.save(update_fields=["status", "error_message", "updated_at"])
            messages.warning(request, f"Amazon settings were saved, but the connection test failed: {exc}")
        if ajax:
            return JsonResponse({"ok": save_ok, "message": save_message, "status": connection.status, "mapped_skus": MarketplaceListing.objects.filter(connection=connection, is_active=True).count()})
        return redirect("backoffice:amazon-integration")


class SuperAdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = reverse_lazy("backoffice:login")
    session_user_key = "backoffice_user_id"

    def get_portal_user(self):
        user_id = self.request.session.get(self.session_user_key)
        if user_id:
            user = User.objects.filter(pk=user_id, is_active=True).first()
            if user:
                return user
            self.request.session.pop(self.session_user_key, None)
        return None

    def dispatch(self, request, *args, **kwargs):
        self.portal_user = self.get_portal_user()
        if self.portal_user:
            request.user = self.portal_user
        return super().dispatch(request, *args, **kwargs)

    def test_func(self):
        user = getattr(self, "portal_user", None)
        return bool(user) and user.is_authenticated and (
            user.is_superuser
            or user.global_roles.filter(role__code=ROLE_SUPER_ADMIN, account_membership__isnull=True).exists()
        )

    def get_context_data(self, **kwargs):
        """Expose real, relevant notifications in every backoffice view."""
        context = super().get_context_data(**kwargs)
        user = getattr(self, "portal_user", None) or self.request.user
        notification_queryset = Notification.objects.filter(Q(user__isnull=True) | Q(user=user))
        notifications = notification_queryset.order_by("-created_at")[:8]
        context.update({
            "backoffice_notifications": notifications,
            "backoffice_unread_notification_count": notification_queryset.filter(read_at__isnull=True).count(),
        })
        return context

    def handle_no_permission(self):
        # The URL selects the portal. Never send an unauthenticated or
        # retailer-session request from /admin/ to the retailer portal.
        return redirect(self.login_url)


class BackofficeStorePreviewView(SuperAdminRequiredMixin, TemplateView):
    template_name = "backoffice/store_preview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "page_title": "Store Preview",
            "preview_stores": Store.objects.filter(
                status=Store.STATUS_ACTIVE, is_active=True
            ).select_related("retailer").order_by("retailer__display_name", "name"),
            "active_group": "Commerce",
            "sidebar_groups": grouped_modules(),
        })
        return context


class BackofficeOfflineSalesView(SuperAdminRequiredMixin, TemplateView):
    template_name = "backoffice/offline_sales.html"

    def post(self, request, *args, **kwargs):
        sale_id = request.POST.get("sale_id")
        if sale_id:
            sale = get_object_or_404(OfflineSale, pk=sale_id)
            action = request.POST.get("action")
            try:
                if action == "delete-permanent":
                    if sale.is_active:
                        messages.error(request, "Move the sale to trash before permanently deleting it.")
                    else:
                        sale.delete()
                        messages.success(request, "Offline sale permanently deleted.")
                elif action in {"delete", "restore"}:
                    set_offline_sale_active(sale, action == "restore", actor=getattr(self, "portal_user", request.user))
                    messages.success(request, f"Offline sale {('restored' if action == 'restore' else 'moved to trash')}.")
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect("backoffice:offline-sales")
        retailer = get_object_or_404(Retailer, pk=request.POST.get("retailer_id"))
        enabled = request.POST.get("enabled") == "on"
        set_offline_sales_enabled(retailer, enabled, actor=getattr(self, "portal_user", request.user))
        messages.success(request, f"Offline Sales {('enabled' if enabled else 'disabled')} for {retailer.display_name or retailer.legal_name}.")
        return redirect("backoffice:offline-sales")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        retailers = Retailer.objects.select_related("account").filter(is_active=True).order_by("display_name", "legal_name")
        setting_map = {
            setting.key.rsplit(".", 1)[-1]: setting
            for setting in Setting.objects.filter(key__startswith="retailer.offline_sales.")
        }
        retailer_rows = []
        for retailer in retailers:
            setting = setting_map.get(str(retailer.pk))
            retailer_rows.append({
                "retailer": retailer,
                "enabled": bool((setting.value or {}).get("enabled", True)) if setting else True,
            })
        sales = OfflineSale.objects.select_related("store", "product", "product__retailer", "created_by").order_by("-sold_at")
        context.update({
            "page_title": "Offline Sales Tracking",
            "active_group": "Operations",
            "sidebar_groups": grouped_modules(),
            "offline_retailer_rows": retailer_rows,
            "offline_sales": sales[:100],
            "offline_sales_count": sales.count(),
            "offline_sales_revenue": sales.aggregate(total=Sum("total_amount"))["total"] or 0,
        })
        return context


class BackofficeOfflineSaleEditView(SuperAdminRequiredMixin, UpdateView):
    model = OfflineSale
    form_class = OfflineSaleForm
    template_name = "backoffice/offline_sale_edit.html"

    def get_queryset(self):
        return OfflineSale.objects.select_related("product__retailer", "store", "delivery_location")

    def get_form(self, form_class=None):
        retailer = self.object.product.retailer
        form = self.form_class(self.request.POST or None, instance=self.object, retailer=retailer, store=self.object.store, initial={"brand": self.object.product.brand_id, "delivery_location": self.object.delivery_location_id})
        for field_name in ("store", "brand", "product", "variant", "quantity"):
            form.fields[field_name].disabled = True
        return form

    def form_valid(self, form):
        sale = form.save(commit=False)
        sale.warehouse = self.object.warehouse
        sale.store = self.object.store
        sale.product = self.object.product
        sale.variant = self.object.variant
        sale.quantity = self.object.quantity
        sale.total_amount = sale.unit_price * sale.quantity
        sale.delivery_location = form.cleaned_data.get("delivery_location", sale.delivery_location)
        sale.selected_pincode = form.cleaned_data.get("selected_pincode", sale.selected_pincode)
        sale.save(update_fields=["delivery_location", "selected_pincode", "unit_price", "sold_at", "note", "total_amount", "updated_at"])
        messages.success(self.request, "Offline sale updated successfully.")
        return redirect("backoffice:offline-sales")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"page_title": "Edit Offline Sale", "active_group": "Operations", "sidebar_groups": grouped_modules()})
        return context
        return context

class AmazonRetailerMenuSettingsView(SuperAdminRequiredMixin, View):
    template_name = "backoffice/amazon_retailer_menu_settings.html"

    def _context(self, form):
        return {"form": form, "page_title": "Retailer Menu Visibility", "active_group": "Amazon SP-API", "sidebar_groups": grouped_modules()}

    def _initial(self):
        menu = MarketplaceSetting.objects.filter(key="amazon_retailer_menu_enabled").values_list("value", flat=True).first() or {}
        orders = MarketplaceSetting.objects.filter(key="amazon_orders_retailer_menu_enabled").values_list("value", flat=True).first() or {}
        return {"show_retailer_menu": bool(menu.get("enabled", False)), "show_retailer_orders": bool(orders.get("enabled", False))}

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._context(AmazonRetailerMenuSettingsForm(initial=self._initial())))

    def post(self, request, *args, **kwargs):
        form = AmazonRetailerMenuSettingsForm(request.POST)
        if form.is_valid():
            MarketplaceSetting.objects.update_or_create(key="amazon_retailer_menu_enabled", defaults={"value": {"enabled": form.cleaned_data["show_retailer_menu"]}})
            MarketplaceSetting.objects.update_or_create(key="amazon_orders_retailer_menu_enabled", defaults={"value": {"enabled": form.cleaned_data["show_retailer_orders"]}})
            messages.success(request, "Retailer Amazon menu visibility saved successfully.")
            return redirect("backoffice:amazon-retailer-menu-settings")
        return render(request, self.template_name, self._context(form))


class BackofficeSecurityView(SuperAdminRequiredMixin, View):
    template_name = "backoffice/security.html"

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._context(SuperAdminSecurityForm(user=self.portal_user)))

    def post(self, request, *args, **kwargs):
        form = SuperAdminSecurityForm(request.POST, user=self.portal_user)
        if form.is_valid():
            user = self.portal_user
            user.email = form.cleaned_data["email"]
            changed_fields = ["email", "updated_at"]
            if form.cleaned_data.get("new_password"):
                user.set_password(form.cleaned_data["new_password"])
                changed_fields.append("password")
            user.save(update_fields=changed_fields)
            messages.success(request, "Super Admin login details updated successfully.")
            return redirect("backoffice:security")
        return render(request, self.template_name, self._context(form))

    def _context(self, form):
        return {"form": form, "page_title": "Security Settings", "active_group": "Platform", "sidebar_groups": grouped_modules()}


class AmazonOrderTrackingAdminView(SuperAdminRequiredMixin, TemplateView):
    template_name = "backoffice/amazon_orders.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        orders = AmazonOrderTracking.objects.select_related("retailer", "store", "connection", "local_order").prefetch_related("items").order_by("-purchase_date", "-created_at")
        context.update({
            "page_title": "Amazon Order Tracking", "active_group": "Amazon SP-API", "sidebar_groups": grouped_modules(),
            "amazon_orders": orders[:200], "amazon_order_count": orders.count(),
            "amazon_pending_count": orders.filter(amazon_order_status__in=["Pending", "Unshipped", "PartiallyShipped"]).count(),
            "amazon_unattributed_count": orders.filter(attribution_status__in=["pending_items", "multiple_stores"]).count(),
        })
        return context


class AmazonCatalogAdminView(SuperAdminRequiredMixin, View):
    template_name = "backoffice/amazon_catalog.html"

    def _connection(self):
        connector = MarketplaceConnector.objects.filter(code="amazon").first()
        return MarketplaceConnection.objects.filter(connector=connector).first() if connector else None

    def _snapshot(self, connection):
        listings = MarketplaceListing.objects.filter(connection=connection).select_related("product", "product__store", "variant", "fulfillment_location").order_by("seller_sku") if connection else MarketplaceListing.objects.none()
        latest = MarketplaceSyncJob.objects.filter(connection=connection, job_type=MarketplaceSyncJob.TYPE_PRODUCT_SYNC, direction=MarketplaceSyncJob.DIRECTION_INBOUND, status=MarketplaceSyncJob.STATUS_COMPLETED).order_by("-created_at").first() if connection else None
        result = (latest.result or {}) if latest else {}
        remote_items = result.get("items", []) or []
        listing_by_sku = {listing.seller_sku: listing for listing in listings}
        listing_rows = []
        if latest:
            # The latest Amazon import is authoritative. Do not display old
            # local fallback SKUs as Amazon listings; that was the reason
            # entries such as SGS24 appeared as pending beside real offers.
            for item in remote_items:
                sku = item.get("sku")
                if not sku:
                    continue
                listing = listing_by_sku.get(sku)
                product = listing.product if listing else None
                variant = listing.variant if listing else None
                product_label = product.name if product else "Not matched in Nuboxed"
                if variant:
                    product_label = f"{product_label} · {variant.name}"
                listing_rows.append({
                    "sku": sku,
                    "asin": item.get("asin") or (listing.external_listing_id if listing else "—") or "—",
                    "marketplace": item.get("marketplace_id") or (listing.marketplace_id if listing else "—"),
                    "product": product_label,
                    "store": product.store.name if product else "—",
                    "warehouse": listing.fulfillment_location.name if listing and listing.fulfillment_location else "Auto / retailer stock" if product else "—",
                    "quantity": item.get("quantity") if item.get("quantity") is not None else (listing.last_pulled_quantity if listing and listing.last_pulled_quantity is not None else 0),
                    "status": "active" if listing else "unmatched",
                    "source": "Amazon ↔ Nuboxed" if listing and listing.last_pushed_at else "Amazon → Nuboxed",
                    "error": "" if listing else "Amazon Seller SKU is not mapped to a Nuboxed product or variant.",
                })
            remote_skus = {item.get("sku") for item in remote_items if item.get("sku")}
            # Show local mappings that were pushed outbound but are not in the
            # current Amazon import, including rejected or processing offers.
            for listing in listings:
                if listing.seller_sku in remote_skus:
                    continue
                product_label = listing.product.name
                if listing.variant:
                    product_label = f"{product_label} · {listing.variant.name}"
                listing_rows.append({
                    "sku": listing.seller_sku,
                    "asin": listing.external_listing_id or "—",
                    "marketplace": listing.marketplace_id or "—",
                    "product": product_label,
                    "store": listing.product.store.name if listing.product.store else "—",
                    "warehouse": listing.fulfillment_location.name if listing.fulfillment_location else "Auto / retailer stock",
                    "quantity": listing.last_pushed_quantity if listing.last_pushed_quantity is not None else 0,
                    "status": listing.status,
                    "source": "Nuboxed → Amazon",
                    "error": listing.last_error,
                })
        else:
            listing_rows = [{"sku": x.seller_sku, "asin": x.external_listing_id or "—", "marketplace": x.marketplace_id, "product": f"{x.product.name}{f' · {x.variant.name}' if x.variant else ''}", "store": x.product.store.name, "warehouse": x.fulfillment_location.name if x.fulfillment_location else "Auto / retailer stock", "quantity": x.last_pulled_quantity if x.last_pulled_quantity is not None else (x.last_pushed_quantity if x.last_pushed_quantity is not None else 0), "status": x.status, "source": "Nuboxed → Amazon", "error": x.last_error} for x in listings[:500]]
        return {
            "import_status": latest.status if latest else "not_run",
            "imported_count": result.get("imported_count", 0),
            "matched_count": result.get("matched_count", 0),
            "unmatched_count": result.get("unmatched_count", 0),
            "last_import": latest.created_at.isoformat() if latest else None,
            "listings": listing_rows,
        }

    def get(self, request):
        connection = self._connection()
        if request.GET.get("snapshot") == "1":
            return JsonResponse({"ok": True, **self._snapshot(connection)})
        context = {"connection": connection, "page_title": "Amazon Catalog", "active_group": "Amazon SP-API", "sidebar_groups": grouped_modules(), "snapshot": self._snapshot(connection)}
        return render(request, self.template_name, context)

    def post(self, request):
        connection = self._connection()
        if not connection:
            return JsonResponse({"ok": False, "message": "Configure the Amazon connection first."}, status=400)
        pending = MarketplaceSyncJob.objects.filter(connection=connection, job_type=MarketplaceSyncJob.TYPE_PRODUCT_SYNC, direction=MarketplaceSyncJob.DIRECTION_INBOUND, status__in=(MarketplaceSyncJob.STATUS_PENDING, MarketplaceSyncJob.STATUS_PROCESSING)).exists()
        job = None
        if not pending:
            job = enqueue_sync_job(connection, MarketplaceSyncJob.TYPE_PRODUCT_SYNC, MarketplaceSyncJob.DIRECTION_INBOUND)
        # The catalog button is an explicit manual action. Execute that one
        # job now so a local install does not silently depend on a Celery
        # worker being started; the UI remains AJAX and never reloads.
        if job and request.POST.get("execute") == "1":
            process_sync_job(job)
            if job.status == MarketplaceSyncJob.STATUS_FAILED:
                return JsonResponse({"ok": False, "message": job.error_message or "Amazon listing import failed."}, status=400)
            return JsonResponse({"ok": True, "message": "Amazon listings imported and reconciled."})
        return JsonResponse({"ok": True, "message": "Amazon listing import queued. This page will update automatically."})


class BackofficeSellerVerificationDocumentsView(SuperAdminRequiredMixin, View):
    template_name = "backoffice/seller_verification_documents.html"

    def _page_setting(self):
        setting, _ = SellerVerificationPageSetting.objects.get_or_create(
            singleton_key="registration",
            defaults={
                "section_title": "Seller Verification Documents",
                "section_description": "Upload documents to speed up your seller verification. All documents are optional during registration — you can upload them later from your profile.",
            },
        )
        return setting

    def _context(self, page_form, document_formset):
        return {
            "page_form": page_form,
            "document_formset": document_formset,
            "active_group": "Platform",
            "sidebar_groups": grouped_modules(),
            "page_title": "Seller Verification Documents",
        }

    def get(self, request, *args, **kwargs):
        document_formset_class = modelformset_factory(
            SellerVerificationDocumentSetting,
            form=SellerVerificationDocumentSettingForm,
            extra=0,
        )
        return render(
            request,
            self.template_name,
            self._context(
                SellerVerificationPageSettingForm(instance=self._page_setting()),
                document_formset_class(queryset=SellerVerificationDocumentSetting.objects.filter(is_active=True)),
            ),
        )

    def post(self, request, *args, **kwargs):
        document_formset_class = modelformset_factory(
            SellerVerificationDocumentSetting,
            form=SellerVerificationDocumentSettingForm,
            extra=0,
        )
        page_form = SellerVerificationPageSettingForm(request.POST, instance=self._page_setting())
        document_formset = document_formset_class(
            request.POST,
            queryset=SellerVerificationDocumentSetting.objects.filter(is_active=True),
        )
        if page_form.is_valid() and document_formset.is_valid():
            page_form.save()
            document_formset.save()
            messages.success(request, "Seller verification document settings saved.")
            return redirect("backoffice:seller-verification-documents")
        return render(request, self.template_name, self._context(page_form, document_formset))


class BackofficeSellerVerificationDocumentCreateView(SuperAdminRequiredMixin, View):
    template_name = "backoffice/seller_verification_document_create.html"

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {
            "form": SellerVerificationDocumentCreateForm(),
            "active_group": "Platform", "sidebar_groups": grouped_modules(),
            "page_title": "Add Seller Verification Field",
        })

    def post(self, request, *args, **kwargs):
        form = SellerVerificationDocumentCreateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "New seller verification field added.")
            return redirect("backoffice:seller-verification-documents")
        return render(request, self.template_name, {"form": form, "active_group": "Platform", "sidebar_groups": grouped_modules(), "page_title": "Add Seller Verification Field"})


class BackofficeRetailerRegistrationFieldsView(SuperAdminRequiredMixin, View):
    template_name = "backoffice/retailer_registration_fields.html"

    def _formset(self, *args, **kwargs):
        return modelformset_factory(RetailerRegistrationFieldSetting, form=RetailerRegistrationFieldForm, extra=0)(*args, queryset=RetailerRegistrationFieldSetting.objects.filter(is_active=True), **kwargs)

    def _context(self, formset, new_form=None):
        return {"formset": formset, "new_form": new_form or RetailerRegistrationFieldForm(), "active_group": "Platform", "sidebar_groups": grouped_modules(), "page_title": "Retailer Registration Fields"}

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._context(self._formset()))

    def post(self, request, *args, **kwargs):
        delete_id = request.POST.get("delete_field")
        if delete_id:
            setting = get_object_or_404(RetailerRegistrationFieldSetting, pk=delete_id)
            if setting.is_system:
                messages.error(request, "System fields can be hidden but cannot be deleted.")
            else:
                setting.delete()
                messages.success(request, "Retailer registration field removed.")
            return redirect("backoffice:retailer-registration-fields")
        if "add_field" in request.POST:
            new_form = RetailerRegistrationFieldForm(request.POST)
            if new_form.is_valid():
                new_form.save()
                messages.success(request, "Retailer registration field added.")
                return redirect("/admin/retailer-registration-fields/?added=1")
            return render(request, self.template_name, self._context(self._formset(), new_form))
        # Keep the immutable field key server-side as a safety net for an older
        # cached page that was opened before the hidden field_name input existed.
        # The key is displayed as read-only in the grid and must never be lost.
        post_data = request.POST.copy()
        current_settings = list(RetailerRegistrationFieldSetting.objects.filter(is_active=True))
        for index, setting in enumerate(current_settings):
            post_data.setdefault(f"form-{index}-field_name", setting.field_name)
        formset = self._formset(post_data)
        if formset.is_valid():
            formset.save()
            # Checkbox inputs are omitted from POST when unchecked. Persist
            # the two toggle values explicitly by form prefix so a hidden
            # field can never be silently restored to its old value.
            for form in formset.forms:
                setting = form.instance
                prefix = form.prefix
                setting.is_visible = request.POST.get(f"{prefix}-is_visible") in {"1", "on", "true"}
                setting.is_required = request.POST.get(f"{prefix}-is_required") in {"1", "on", "true"}
                setting.save(update_fields=["is_visible", "is_required", "updated_at"])
            messages.success(request, "Retailer registration fields saved.")
            return redirect("/admin/retailer-registration-fields/?saved=1")
        messages.error(request, "Fields could not be saved. Please check the highlighted values.")
        return render(request, self.template_name, self._context(formset))


class BackofficeRetailerRegistrationFieldCreateView(SuperAdminRequiredMixin, View):
    template_name = "backoffice/retailer_registration_field_create.html"

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {"form": RetailerRegistrationFieldForm(), "active_group": "Platform", "sidebar_groups": grouped_modules(), "page_title": "Add Retailer Registration Field"})

    def post(self, request, *args, **kwargs):
        form = RetailerRegistrationFieldForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Retailer registration field added.")
            return redirect("/admin/retailer-registration-fields/?saved=1")
        return render(request, self.template_name, {"form": form, "active_group": "Platform", "sidebar_groups": grouped_modules(), "page_title": "Add Retailer Registration Field"})


class BackofficeRetailerRegistrationFieldDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        setting = get_object_or_404(RetailerRegistrationFieldSetting, pk=pk)
        if setting.is_system:
            messages.error(request, "System fields can be hidden but cannot be deleted.")
        else:
            setting.delete()
            messages.success(request, "Retailer registration field removed.")
        return redirect("backoffice:retailer-registration-fields")

class BackofficeHomepageSettingsView(SuperAdminRequiredMixin, View):
    template_name = "backoffice/homepage_settings.html"

    def page_context(self, settings_form, trust_formset, review_formset):
        return {
            "settings_form": settings_form,
            "trust_formset": trust_formset,
            "review_formset": review_formset,
            "module_key_active": "homepage-settings",
            "active_group": "Page Settings",
            "sidebar_groups": grouped_modules(),
            "page_title": "Homepage Settings",
        }

    def get_settings(self):
        settings, _ = HomePageSettings.objects.get_or_create(singleton_key="homepage")
        return settings

    def get(self, request, *args, **kwargs):
        settings = self.get_settings()
        return render(request, self.template_name, self.page_context(
            HomePageSettingsForm(instance=settings),
            HomeTrustCardFormSet(instance=settings, prefix="trust"),
            HomeReviewCardFormSet(instance=settings, prefix="reviews"),
        ))

    def post(self, request, *args, **kwargs):
        settings = self.get_settings()
        bulk_action = request.POST.get("bulk_action", "")
        bulk_kind, action = bulk_action.split(":", 1) if ":" in bulk_action else ("", "")
        if action in {"delete", "restore", "permanent_delete"} and bulk_kind in {"trust", "reviews"}:
            model = HomeTrustCard if bulk_kind == "trust" else HomeReviewCard
            ids = request.POST.getlist("selected_items")
            queryset = model.objects.filter(settings=settings, id__in=ids)
            if action == "permanent_delete":
                queryset.delete()
                messages.success(request, f"{len(ids)} selected item(s) permanently deleted.")
            else:
                queryset.update(is_active=(action == "restore"))
                messages.success(request, f"{len(ids)} selected item(s) {('restored' if action == 'restore' else 'moved to trash')}.")
            return redirect("backoffice:homepage-settings")
        settings_form = HomePageSettingsForm(request.POST, instance=settings)
        trust_formset = HomeTrustCardFormSet(request.POST, request.FILES, instance=settings, prefix="trust")
        review_formset = HomeReviewCardFormSet(request.POST, request.FILES, instance=settings, prefix="reviews")
        if settings_form.is_valid() and trust_formset.is_valid() and review_formset.is_valid():
            settings_form.save()
            trust_formset.save()
            review_formset.save()
            messages.success(request, "Homepage settings saved successfully.")
            if request.POST.get("save_action") == "close":
                return redirect("backoffice:pages")
            return redirect("backoffice:homepage-settings")
        return render(request, self.template_name, self.page_context(settings_form, trust_formset, review_formset))


@method_decorator([never_cache, ensure_csrf_cookie], name="dispatch")
class BackofficeLoginView(LoginView):
    template_name = "backoffice/login.html"
    authentication_form = BackofficeLoginForm
    redirect_authenticated_user = False
    session_user_key = SuperAdminRequiredMixin.session_user_key

    def dispatch(self, request, *args, **kwargs):
        portal_user = None
        portal_user_id = request.session.get(self.session_user_key)
        if portal_user_id:
            portal_user = User.objects.filter(pk=portal_user_id, is_active=True).first()
        if portal_user and (
            portal_user.is_superuser
            or portal_user.global_roles.filter(role__code=ROLE_SUPER_ADMIN, account_membership__isnull=True).exists()
        ):
            return redirect("backoffice:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        valid, message = verify_captcha(self.request, "admin_login")
        if not valid:
            form.add_error(None, message)
            return self.form_invalid(form)
        self.request.session[self.session_user_key] = str(form.get_user().pk)
        self.request.session.modified = True
        return redirect(self.get_success_url())

    def get_success_url(self):
        # The admin portal must never redirect to the retailer portal.  An
        # admin account may also have a retailer membership, but the portal
        # selected by the login URL is authoritative.
        return reverse("backoffice:dashboard")


class BackofficeLogoutView(LogoutView):
    next_page = reverse_lazy("backoffice:login")

    def get(self, request, *args, **kwargs):
        request.session.pop(SuperAdminRequiredMixin.session_user_key, None)
        return redirect(self.next_page)

    def post(self, request, *args, **kwargs):
        request.session.pop(SuperAdminRequiredMixin.session_user_key, None)
        return redirect(self.next_page)


class BackofficeStoreRatingListView(SuperAdminRequiredMixin, TemplateView):
    template_name = "backoffice/store_ratings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "page_title": "Store Ratings",
            "ratings": StoreRating.objects.select_related("store", "store__retailer").order_by("-created_at"),
            "rating_action_url_name": "backoffice:store-rating-action",
            "rating_portal": "admin",
            "sidebar_groups": grouped_modules(),
            "module_key_active": "store-ratings",
            "active_group": "Commerce",
        })
        return context


class BackofficeStoreRatingActionView(SuperAdminRequiredMixin, View):
    VALID_ACTIONS = {"approve", "disapprove", "delete", "restore", "delete-permanent"}

    def post(self, request, action):
        if action not in self.VALID_ACTIONS:
            raise Http404("Unknown rating action.")
        ids = request.POST.getlist("ratings")
        ratings = StoreRating.objects.filter(id__in=ids).select_related("store")
        stores = set(rating.store for rating in ratings)
        count = ratings.count()
        for rating in ratings:
            if action == "approve":
                rating.is_approved, rating.is_active = True, True
                rating.save(update_fields=["is_approved", "is_active", "updated_at"])
            elif action == "disapprove":
                rating.is_approved = False
                rating.save(update_fields=["is_approved", "updated_at"])
            elif action == "delete":
                rating.is_active = False
                rating.save(update_fields=["is_active", "updated_at"])
            elif action == "restore":
                rating.is_active = True
                rating.save(update_fields=["is_active", "updated_at"])
            else:
                rating.delete()
        for store in stores:
            StoreRating.refresh_store_average(store)
        messages.success(request, f"{count} rating(s) updated.")
        return redirect("backoffice:store-ratings")


class RegistryMixin:
    module = None

    def get_module_config(self):
        module = self.kwargs.get("module", self.module)
        if module not in MODULES:
            raise Http404("Unknown module.")
        config = MODULES[module]
        if config.get("group") in {"Operations", "Merchandising"} and module != "inventory":
            raise Http404("This admin section has been removed.")
        return module, config

    def get_model(self):
        return self.get_module_config()[1]["model"]

    def get_base_queryset(self):
        module, config = self.get_module_config()
        queryset = config["model"].objects.all().order_by("-created_at")
        if module == "attributes":
            # Filter out deleted attributes by default
            queryset = queryset.filter(deleted_at__isnull=True)
            queryset = queryset.annotate(
                color_priority=Case(
                    When(code="color", then=Value(0)),
                    When(name__iexact="color", then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            ).order_by("color_priority", "name")
        if module in ("products", "featured-products"):
            queryset = queryset.filter(deleted_at__isnull=True)
        if config.get("base_filters"):
            queryset = queryset.filter(**config["base_filters"])
        return queryset

    def get_trash_field(self, model=None):
        model = model or self.get_model()
        field_names = {field.name for field in model._meta.fields}
        if "deleted_at" in field_names:
            return "deleted_at"
        if "is_active" in field_names:
            return "is_active"
        return None

    def filter_trash_queryset(self, queryset, deleted_status):
        trash_field = self.get_trash_field(queryset.model)
        if trash_field == "deleted_at":
            if deleted_status == "deleted":
                return queryset.filter(deleted_at__isnull=False)
            if deleted_status == "all":
                return queryset
            return queryset.filter(deleted_at__isnull=True)
        if trash_field == "is_active":
            if deleted_status == "deleted":
                return queryset.filter(is_active=False)
            if deleted_status == "all":
                return queryset
            return queryset.filter(is_active=True)
        return queryset

    def soft_delete_object(self, obj):
        trash_field = self.get_trash_field(type(obj))
        if trash_field == "deleted_at":
            obj.deleted_at = timezone.now()
            if hasattr(obj, "is_active"):
                obj.is_active = False
                obj.save(update_fields=["deleted_at", "is_active", "updated_at"])
            else:
                obj.save(update_fields=["deleted_at", "updated_at"])
            return
        if trash_field == "is_active":
            obj.is_active = False
            obj.save(update_fields=["is_active", "updated_at"])
            return
        raise ValueError("This module does not support trash actions.")

    def restore_object(self, obj):
        trash_field = self.get_trash_field(type(obj))
        if trash_field == "deleted_at":
            obj.deleted_at = None
            if hasattr(obj, "is_active"):
                obj.is_active = True
                obj.save(update_fields=["deleted_at", "is_active", "updated_at"])
            else:
                obj.save(update_fields=["deleted_at", "updated_at"])
            return
        if trash_field == "is_active":
            obj.is_active = True
            obj.save(update_fields=["is_active", "updated_at"])
            return
        raise ValueError("This module does not support trash actions.")

    def get_module_form_class(self):
        module, _ = self.get_module_config()
        if module == "users":
            if isinstance(self, BackofficeModuleCreateView):
                return BackofficeUserCreateForm
            return BackofficeUserUpdateForm
        if module == "retailers" and isinstance(self, BackofficeModuleCreateView):
            return BackofficeRetailerCreateForm
        if module == "retailers":
            return BackofficeRetailerUpdateForm
        if module == "attributes":
            return BackofficeProductAttributeForm
        if module == "permissions":
            return BackofficePermissionForm
        if module in ("categories", "featured-categories"):
            return BackofficeCategoryForm
        if module in ("products", "featured-products"):
            return BackofficeProductForm
        if module == "stores":
            return BackofficeStoreForm
        if module == "courier-partners":
            return CourierPartnerForm
        if module == "warehouses":
            return WarehouseForm
        if module == "sliders":
            return BackofficeSliderForm
        if module == "brand-settings":
            return BackofficeBrandSettingsForm
        model = self.get_model()
        excluded = ["created_at", "updated_at"]
        return modelform_factory(model, exclude=excluded)

    def get_color_value_rows(self, attribute):
        if not attribute:
            return []
        rows = []
        for value in attribute.values.order_by("sort_order", "label"):
            palette = value.hex_palette or ([value.hex_color] if value.hex_color else [])
            rows.append(
                {
                    "id": str(value.id),
                    "label": value.label,
                    "mode": "multi" if len(palette) > 1 else "single",
                    "colors": palette if attribute.data_type == ProductAttribute.TYPE_COLOR else [],
                }
            )
        return rows

    def save_color_values(self, attribute, payload):
        try:
            rows = json.loads(payload or "[]")
        except json.JSONDecodeError:
            rows = []

        keep_ids = []
        next_sort = 0
        for row in rows:
            label = (row.get("label") or "").strip()
            colors = [color.strip() for color in row.get("colors", []) if isinstance(color, str) and color.strip()]
            if attribute.data_type == ProductAttribute.TYPE_COLOR:
                if not label or not colors:
                    continue
            elif not label:
                continue
            attr_value = None
            value_id = row.get("id")
            if value_id:
                attr_value = attribute.values.filter(id=value_id).first()
            if attr_value is None:
                attr_value = AttributeValue(attribute=attribute)

            attr_value.label = label
            attr_value.value = label
            attr_value.hex_color = colors[0] if attribute.data_type == ProductAttribute.TYPE_COLOR else ""
            attr_value.hex_palette = colors if attribute.data_type == ProductAttribute.TYPE_COLOR else []
            attr_value.sort_order = next_sort
            attr_value.save()
            keep_ids.append(attr_value.id)
            next_sort += 1

        attribute.values.exclude(id__in=keep_ids).delete()

    def get_sidebar_groups(self):
        return grouped_modules()


class BackofficeInventoryView(SuperAdminRequiredMixin, TemplateView):
    template_name = "backoffice/inventory.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        stock_items = (
            canonical_stock_items(StockItem.objects.all())
            .select_related("product", "product__store", "variant", "warehouse", "warehouse__store")
            .annotate(store_name=Coalesce(F("product__store__name"), F("warehouse__store__name")))
            .order_by("store_name", "product__name", "variant__name")
        )
        store_id = self.request.GET.get("store")
        if store_id:
            stock_items = stock_items.filter(Q(product__store_id=store_id) | Q(warehouse__store_id=store_id))
        context.update({
            "page_title": "Inventory",
            "stock_items": stock_items,
            "stores": Store.objects.filter(is_active=True).order_by("name"),
            "selected_store": store_id or "",
            "sidebar_groups": grouped_modules(),
            "module_key_active": "inventory",
            "active_group": "Operations",
        })
        return context


class BackofficeDashboardView(SuperAdminRequiredMixin, TemplateView):
    template_name = "backoffice/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        total_users = User.objects.filter(is_active=True).count()
        retailer_count = Retailer.objects.filter(is_active=True).count()
        store_count = MODULES["stores"]["model"].objects.filter(is_active=True).count()
        product_count = Product.objects.filter(is_active=True, deleted_at__isnull=True).count()
        pending_retailers = Retailer.objects.filter(status=Retailer.STATUS_PENDING, is_active=True).count()
        pending_products = Product.objects.filter(
            status=Product.STATUS_PENDING, is_active=True, deleted_at__isnull=True
        ).count()
        unread_notifications = context["backoffice_unread_notification_count"]
        dashboard_cards = [
            {"label": "Active Retailers", "value": retailer_count, "trend": f"{pending_retailers} pending", "tone": "emerald"},
            {"label": "Active Stores", "value": store_count, "trend": "Current total", "tone": "blue"},
            {"label": "Live Products", "value": product_count, "trend": f"{pending_products} pending", "tone": "amber"},
            {"label": "Active Users", "value": total_users, "trend": f"{unread_notifications} unread alerts", "tone": "rose"},
        ]
        quick_panels = [
            {"title": "Commerce Control", "items": [("Retailers", "retailers"), ("Stores", "stores"), ("Products", "products"), ("Categories", "categories")]},
            {"title": "Storefront Content", "items": [("Page Texts", "pagetext"), ("Menu Items", "menuitem")]},
        ]
        today = timezone.localdate()
        chart_dates = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
        performance_chart_series = []
        for date in chart_dates:
            start = timezone.make_aware(datetime.combine(date, datetime.min.time()))
            end = start + timedelta(days=1)
            performance_chart_series.append(
                User.objects.filter(created_at__gte=start, created_at__lt=end).count()
                + Retailer.objects.filter(created_at__gte=start, created_at__lt=end).count()
                + Product.objects.filter(created_at__gte=start, created_at__lt=end).count()
            )
        context.update(
            {
                "page_title": "Executive Dashboard",
                "dashboard_cards": dashboard_cards,
                "quick_panels": quick_panels,
                "sidebar_groups": grouped_modules(),
                "module_key_active": None,
                "active_group": "",
                "activity_items": [
                    {"label": f"{pending_retailers} retailer approval(s) pending", "url": reverse("backoffice:module-list", kwargs={"module": "retailers"}) + "?status=pending_approval"},
                    {"label": f"{pending_products} product approval(s) pending", "url": reverse("backoffice:module-list", kwargs={"module": "products"}) + "?status=pending_approval"},
                    {"label": f"{unread_notifications} unread notification(s)", "url": reverse("backoffice:notifications")},
                ],
                "performance_chart_labels": [date.strftime("%d %b") for date in chart_dates],
                "performance_chart_series": performance_chart_series,
                "traffic_chart_series": [retailer_count, store_count, product_count],
            }
        )
        return context


class BackofficeOrdersView(SuperAdminRequiredMixin, TemplateView):
    template_name = "backoffice/orders.html"
    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs)
        c.update({"page_title": "Orders", "orders": Order.objects.select_related("customer", "retailer").prefetch_related("timeline_entries__actor").order_by("-created_at"), "sidebar_groups": grouped_modules(), "module_key_active": None, "active_group": "Commerce"})
        return c


class BackofficeCouponSettingsView(SuperAdminRequiredMixin, View):
    template_name = "backoffice/coupon_settings.html"

    def get(self, request):
        return render(request, self.template_name, self.context())

    def post(self, request):
        Setting.objects.update_or_create(
            key="coupon_feature",
            defaults={"value": {"enabled": request.POST.get("enabled") == "on"}, "is_active": True},
        )
        messages.success(request, "Coupon feature availability updated.")
        return redirect("backoffice:coupon-settings")

    def context(self):
        return {
            "page_title": "Coupon Feature Settings",
            "coupon_enabled": coupon_feature_enabled(),
            "sidebar_groups": grouped_modules(),
            "module_key_active": "coupon-settings",
            "active_group": "Commerce",
        }


class BackofficeOrderDetailView(SuperAdminRequiredMixin, TemplateView):
    template_name = "orders/backoffice_detail.html"

    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs)
        order = get_object_or_404(Order.objects.select_related("customer", "retailer", "address").prefetch_related(
            "items__product__media_items", "items__product__phone_variant__phone_model", "items__warehouse",
            "items__variant__attribute_values__attribute", "items__variant__attribute_values__option",
            "timeline_entries", "payment_transactions__gateway", "payment_transactions__refunds", "invoices__items", "shipments__courier_partner",
            "return_requests__timeline_entries", "return_requests__items__order_item__product",
        ), pk=kwargs["pk"])
        order_items = list(order.items.all())
        cancellation_entry = order.timeline_entries.filter(status=Order.STATUS_CANCELLED).order_by("-occurred_at").first()
        refund_transactions = [refund for transaction in order.payment_transactions.all() for refund in transaction.refunds.all()]
        c.update({"page_title": f"Order {order.number}", "order": order, "portal": "admin", "order_detail_page": True, "order_item_count": len(order_items), "order_unit_count": sum(item.quantity for item in order_items), "order_can_cancel": order.status not in {Order.STATUS_CANCELLED, Order.STATUS_DELIVERED, Order.STATUS_RETURNED, Order.STATUS_REFUNDED}, "cancellation_entry": cancellation_entry, "refund_transactions": refund_transactions, "sidebar_groups": grouped_modules(), "module_key_active": None, "active_group": "Commerce"})
        return c


class BackofficeOrderStatusView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk); form = OrderStatusForm(request.POST)
        if form.is_valid():
            updated_order = update_order_status(order, form.cleaned_data["status"], actor=getattr(self, "portal_user", request.user))
            if getattr(updated_order, "_fulfillment_warning", ""):
                messages.warning(request, f"Order status updated, but courier booking is pending: {updated_order._fulfillment_warning}")
        return redirect("backoffice:orders")


class BackofficeOrderCancelView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        if order.status in {Order.STATUS_CANCELLED, Order.STATUS_DELIVERED, Order.STATUS_RETURNED, Order.STATUS_REFUNDED}:
            messages.error(request, "This order cannot be cancelled in its current status.")
        else:
            update_order_status(order, Order.STATUS_CANCELLED, actor=getattr(self, "portal_user", request.user), note=request.POST.get("cancellation_reason", "Customer requested"))
            messages.success(request, f"Order {order.number} was cancelled successfully.")
        return redirect("backoffice:order-detail", pk=order.pk)


class BackofficeOrderTransactionView(SuperAdminRequiredMixin, View):
    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        transactions = PaymentTransaction.objects.filter(order=order).select_related("gateway").prefetch_related("refunds")
        return JsonResponse({"order": order.number, "transactions": [{
            "transaction_number": tx.transaction_number,
            "status": tx.get_status_display(),
            "gateway": tx.gateway.name,
            "amount": str(tx.amount),
            "currency": tx.currency,
            "gateway_transaction_id": tx.gateway_transaction_id or "Not provided",
            "captured_at": tx.captured_at.strftime("%d %b %Y, %H:%M") if tx.captured_at else "Not captured",
            "refunds": [{"number": refund.refund_number, "amount": str(refund.amount), "status": refund.get_status_display(), "reason": refund.reason} for refund in tx.refunds.all()],
        } for tx in transactions]})


class BackofficeOrderRefundView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        transaction = PaymentTransaction.objects.filter(order=order, status=PaymentTransaction.STATUS_CAPTURED).first()
        try:
            if not transaction:
                raise ValueError("No captured payment transaction is available for this order.")
            amount = Decimal(request.POST.get("amount", "0"))
            if amount <= 0:
                raise ValueError("Refund amount must be greater than zero.")
            reason = request.POST.get("reason", "Customer request").strip() or "Customer request"
            refund = process_refund(transaction, amount=amount, reason=reason, actor=getattr(self, "portal_user", request.user))
            if transaction.status == PaymentTransaction.STATUS_REFUNDED:
                update_order_status(order, Order.STATUS_REFUNDED, actor=getattr(self, "portal_user", request.user), note=f"Full payment refund {refund.refund_number} processed: {reason}")
            else:
                build_order_timeline(order, order.status, "Partial refund processed", f"Refund {refund.refund_number} of {amount} {transaction.currency} processed: {reason}", actor=getattr(self, "portal_user", request.user))
            messages.success(request, f"Refund {refund.refund_number} processed successfully.")
        except (ValueError, InvalidOperation) as exc:
            messages.error(request, str(exc))
        return redirect("backoffice:order-detail", pk=order.pk)


class BackofficeOrderAddressUpdateView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        fields = ["shipping_full_name", "shipping_phone", "shipping_address_line1", "shipping_address_line2", "shipping_city", "shipping_state", "shipping_postal_code", "shipping_country_code"]
        for field in fields:
            value = request.POST.get(field, "").strip()
            if field == "shipping_country_code":
                value = value.upper()[:2]
            setattr(order, field, value)
        order.save(update_fields=fields + ["updated_at"])
        messages.success(request, "Shipping address updated successfully.")
        return redirect("backoffice:order-detail", pk=order.pk)


class BackofficeOrderInvoiceView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk); generate_invoice_for_order(order, actor=getattr(self, "portal_user", request.user)); return redirect("backoffice:order-invoice-print", pk=pk)


class BackofficeOrderLabelView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk); generate_delivery_label(order, actor=getattr(self, "portal_user", request.user)); return redirect("backoffice:order-label-print", pk=pk)


@method_decorator(xframe_options_sameorigin, name="dispatch")
class BackofficeOrderInvoicePrintView(SuperAdminRequiredMixin, TemplateView):
    template_name = "orders/invoice_print.html"
    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs); order = get_object_or_404(Order, pk=kwargs["pk"]); invoice = generate_invoice_for_order(order, actor=getattr(self, "portal_user", self.request.user)); shipment = order.shipments.order_by("-created_at").first(); invoice_access_url = build_public_url(self.request, reverse("storefront:invoice-access", kwargs={"invoice_number": invoice.invoice_number})); c.update({"order": order, "invoice": invoice, "invoice_design": Setting.objects.filter(key="invoice_design").values_list("value", flat=True).first() or {}, "tracking_number": getattr(shipment, "tracking_number", ""), "amount_in_words": amount_in_words(invoice.total_amount or order.total_amount, invoice.currency or order.currency_code), "invoice_url_json": json.dumps(invoice_access_url), "invoice_access_url": invoice_access_url}); return c


@method_decorator(xframe_options_sameorigin, name="dispatch")
class BackofficeOrderLabelPrintView(SuperAdminRequiredMixin, TemplateView):
    template_name = "orders/label_print.html"
    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs); order = get_object_or_404(Order, pk=kwargs["pk"]); label = generate_delivery_label(order, actor=getattr(self, "portal_user", self.request.user)); payload = dict(label.payload); verification_url = build_public_url(self.request, reverse("storefront:label-verify", kwargs={"label_number": label.label_number})); payload["tracking_url"] = verification_url; payload["barcode_value"] = verification_url; c.update({"order": order, "label": label, "verification_url": verification_url, "label_payload_json": json.dumps(payload)}); return c


class BackofficeInvoiceDesignView(SuperAdminRequiredMixin, FormView):
    template_name = "backoffice/invoice_design.html"
    def get_initial(self):
        return Setting.objects.filter(key="invoice_design").values_list("value", flat=True).first() or {"company_name": "Nuboxed", "footer_text": "Thank you for your business.", "accent_color": "#e04420"}
    def get_form_class(self):
        from django import forms
        return type("InvoiceDesignForm", (forms.Form,), {"company_name": forms.CharField(required=False), "footer_text": forms.CharField(required=False, widget=forms.Textarea), "accent_color": forms.CharField(required=False)})
    def form_valid(self, form):
        Setting.objects.update_or_create(key="invoice_design", defaults={"value": form.cleaned_data}); messages.success(self.request, "Invoice design saved."); return redirect("backoffice:invoice-design")
    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs); c.update({"page_title": "Invoice Design (Admin only)", "sidebar_groups": grouped_modules(), "module_key_active": None, "active_group": "Platform"}); return c

    def get_sidebar_groups(self):
        return grouped_modules()


class BackofficeFooterSettingsView(SuperAdminRequiredMixin, View):
    template_name = "backoffice/footer_settings.html"

    def _defaults(self):
        labels = ["All Products", "Best Sellers", "Trending Now", "Our Stores", "Contact Us", "Help Center", "Track Order", "Shipping & Delivery", "Returns & Refunds", "Contact Support", "About Nuboxed", "Our Stores", "Contact Us", "Top Deals", "Privacy Policy", "Terms & Conditions", "Cookie Policy", "Accessibility"]
        targets = ["/products/", "/products/", "#n8-products", "/stores/", "/contact/", "/contact/", "/account/orders/", "/contact/", "/account/orders/", "/contact/", "/", "/stores/", "/contact/", "/products/", "/contact/", "/contact/", "/contact/", "/contact/"]
        return {"links": [{"text": text, "target": target, "manual": ""} for text, target in zip(labels, targets)], "trust": [{"title": "Secure checkout", "subtitle": "Protected payments"}, {"title": "Fast delivery", "subtitle": "Reliable order updates"}, {"title": "Easy returns", "subtitle": "Simple return process"}, {"title": "Customer support", "subtitle": "Here when you need us"}], "brand_mode": "text", "brand_image": "", "trust_color": "#ffffff", "trust_muted_color": "#8f99aa", "trust_font": "Inter", "copyright": "© 2026 Nuboxed. All rights reserved.", "copyright_align": "left", "show_payment_images": True, "payment_images": [], "payment_width": 54, "payment_width_unit": "px", "payment_height": 32, "payment_height_unit": "px", "payment_fit": "contain"}

    def get(self, request, *args, **kwargs):
        setting = Setting.objects.filter(key="footer_customization", is_active=True).first()
        values = self._defaults(); values.update(setting.value if setting else {})
        pages = Page.objects.filter(is_active=True, is_published=True).order_by("title")
        brand = BrandSettings.objects.filter(is_active=True).first()
        return render(request, self.template_name, {"settings": values, "brand": brand, "fonts": HomePageSettings.FONT_CHOICES, "pages": pages, "sidebar_groups": grouped_modules(), "active_group": "Page Settings", "page_title": "Footer Settings"})

    def post(self, request, *args, **kwargs):
        links = []
        for index in range(1, 51):
            text = request.POST.get(f"link_text_{index}", "").strip()
            target = request.POST.get(f"link_target_{index}", "").strip()
            manual = request.POST.get(f"link_manual_{index}", "").strip()
            if text:
                links.append({"text": text, "target": target, "manual": manual})
        trust = []
        for index in range(1, 5):
            title = request.POST.get(f"trust_title_{index}", "").strip()
            subtitle = request.POST.get(f"trust_subtitle_{index}", "").strip()
            if title or subtitle:
                trust.append({"title": title, "subtitle": subtitle})
        dimension_units = {"px", "%", "rem", "em", "vw", "vh", "auto"}
        width_unit = request.POST.get("payment_width_unit", "px") if request.POST.get("payment_width_unit", "px") in dimension_units else "px"
        height_unit = request.POST.get("payment_height_unit", "px") if request.POST.get("payment_height_unit", "px") in dimension_units else "px"
        payment_image = next((x.strip() for x in request.POST.get("payment_images", "").splitlines() if x.strip()), "")
        values = {"links": links, "trust": trust, "brand_mode": request.POST.get("brand_mode", "text"), "brand_image": request.POST.get("brand_image", "").strip(), "trust_color": request.POST.get("trust_color", "#ffffff"), "trust_muted_color": request.POST.get("trust_muted_color", "#8f99aa"), "trust_font": request.POST.get("trust_font", "Inter"), "copyright": request.POST.get("copyright", "").strip(), "copyright_align": request.POST.get("copyright_align", "left"), "show_payment_images": request.POST.get("show_payment_images") == "on", "payment_images": [payment_image] if payment_image else [], "payment_width": max(1, min(int(request.POST.get("payment_width") or 54), 1000)), "payment_width_unit": width_unit, "payment_height": max(1, min(int(request.POST.get("payment_height") or 32), 1000)), "payment_height_unit": height_unit, "payment_fit": request.POST.get("payment_fit", "contain")}
        brand = BrandSettings.objects.filter(is_active=True).first()
        if brand:
            brand.brand_name = request.POST.get("brand_name", brand.brand_name).strip() or brand.brand_name
            brand.footer_top_title = request.POST.get("footer_top_title", brand.footer_top_title).strip()
            brand.footer_top_subtitle = request.POST.get("footer_top_subtitle", brand.footer_top_subtitle).strip()
            brand.footer_description = request.POST.get("footer_description", brand.footer_description).strip()
            brand.footer_font_family = request.POST.get("footer_font_family", brand.footer_font_family)
            brand.footer_heading_color = request.POST.get("footer_heading_color", brand.footer_heading_color)
            brand.footer_text_color = request.POST.get("footer_text_color", brand.footer_text_color)
            brand.footer_link_color = request.POST.get("footer_link_color", brand.footer_link_color)
            brand.save(update_fields=["brand_name", "footer_top_title", "footer_top_subtitle", "footer_description", "footer_font_family", "footer_heading_color", "footer_text_color", "footer_link_color", "updated_at"])
        Setting.objects.update_or_create(key="footer_customization", defaults={"value": values, "is_active": True})
        messages.success(request, "Footer settings saved successfully.")
        return redirect("backoffice:footer-settings")


class BackofficeCaptchaSettingsView(SuperAdminRequiredMixin, View):
    template_name = "backoffice/captcha_settings.html"

    def get(self, request, *args, **kwargs):
        values = get_captcha_settings()
        values["secret_saved"] = bool(values.get("secret_key"))
        values["secret_key"] = ""
        return render(request, self.template_name, {"settings": values, "sidebar_groups": grouped_modules(), "active_group": "Platform", "page_title": "Captcha Settings"})

    def post(self, request, *args, **kwargs):
        provider = request.POST.get("provider", "turnstile")
        if provider not in {"turnstile", "hcaptcha", "recaptcha"}:
            provider = "turnstile"
        existing = Setting.objects.filter(key="captcha_settings").first()
        current = existing.value if existing and isinstance(existing.value, dict) else {}
        secret = request.POST.get("secret_key", "").strip()
        values = {
            "enabled": request.POST.get("enabled") == "on",
            "provider": provider,
            "alignment": request.POST.get("alignment", "left") if request.POST.get("alignment", "left") in {"left", "center", "right"} else "left",
            "site_key": request.POST.get("site_key", "").strip(),
            "secret_key": encrypt(secret) if secret else current.get("secret_key", ""),
            "protect_customer_login": request.POST.get("protect_customer_login") == "on",
            "protect_customer_register": request.POST.get("protect_customer_register") == "on",
            "protect_retailer_login": request.POST.get("protect_retailer_login") == "on",
            "protect_admin_login": request.POST.get("protect_admin_login") == "on",
            "protect_public_forms": request.POST.get("protect_public_forms") == "on",
        }
        Setting.objects.update_or_create(key="captcha_settings", defaults={"value": values, "is_active": True})
        messages.success(request, "Captcha settings saved successfully.")
        return redirect("backoffice:captcha-settings")


class BackofficeContactSettingsView(SuperAdminRequiredMixin, View):
    template_name = "backoffice/contact_settings.html"

    def defaults(self):
        defaults = {
            "hero_eyebrow": "We are here to help", "hero_title": "Let’s start a conversation.",
            "hero_description": "Questions about an order, product, partnership or your Nuboxed account? Reach the right team and receive clear, friendly support.",
            "info_heading": "Contact information", "info_description": "Choose the fastest channel for your enquiry. Our team will guide you from there.",
            "form_heading": "Send us a message", "form_description": "Share a few details and the appropriate Nuboxed specialist will contact you.",
            "submit_text": "Send message", "form_note": "By submitting, you agree to our privacy policy and contact terms.",
            "support_eyebrow": "Quick assistance", "support_heading": "Find the right support faster", "support_description": "Use one of these dedicated support paths for common ecommerce enquiries.",
            "support_1_title": "Orders & delivery", "support_1_text": "Track your shipment, update delivery details or report an issue with an order.", "support_2_title": "Returns & refunds", "support_2_text": "Start a return, check refund status or understand our return eligibility policy.", "support_3_title": "Business enquiries", "support_3_text": "Connect with us about retail partnerships, marketplace selling or corporate orders.",
            "faq_eyebrow": "FAQ", "faq_heading": "Before you contact us", "faq_description": "Answers to a few common questions that may save you time.",
            "brand_color": "#e04420", "dark_color": "#5b241b", "icon_color": "#e04420", "heading_weight": "800", "heading_underline": "none", "body_font_size": "16",
            "hero_text_color": "#ffffff", "info_text_color": "#ffffff", "form_text_color": "#111827", "support_text_color": "#111827", "faq_text_color": "#111827", "hero_font": "Inter", "info_font": "Inter", "form_font": "Inter", "support_font": "Inter", "faq_font": "Inter", "info_icon": "fa-solid fa-envelope", "info_phone_icon": "fa-solid fa-phone", "info_location_icon": "fa-solid fa-location-dot", "support_icon_1": "fa-solid fa-box", "support_icon_2": "fa-solid fa-rotate-left", "support_icon_3": "fa-solid fa-handshake", "info_icon_svg": "", "info_icon_image": "", "support_icon_svg_1": "", "support_icon_svg_2": "", "support_icon_svg_3": "", "support_icon_image_1": "", "support_icon_image_2": "", "support_icon_image_3": "",
            "page_bg_color": "#f6f7fb", "hero_bg_mode": "gradient", "hero_bg_color": "#111827", "hero_bg_image": "", "hero_bg_opacity": "72", "hero_bg_blend": "normal", "card_bg_color": "#ffffff", "map_bg_image": "",
            "info_bg_mode": "gradient", "info_bg_color": "#e04420", "info_bg_gradient_color": "#b9381d", "info_bg_image": "", "form_bg_color": "#ffffff", "form_bg_image": "", "support_bg_color": "#ffffff", "support_bg_image": "", "faq_bg_color": "#ffffff", "faq_bg_image": "",
            "faq_items": [{"question": "How quickly will I receive a response?", "answer": "Most messages receive a response within two business hours during support hours. Complex order or payment cases may require additional verification."}, {"question": "What information should I include?", "answer": "Include your order number, registered email or phone number, and a clear description of the issue."}, {"question": "Can I contact you about a partnership?", "answer": "Yes. Select Business partnership in the form or email business@nuboxed.com so the enquiry reaches the appropriate team."}],
            "hero_eyebrow_color": "#ffffff", "hero_eyebrow_font": "Inter", "hero_eyebrow_size": "12", "hero_title_color": "#ffffff", "hero_title_font": "Manrope", "hero_title_size": "72", "hero_description_color": "#d0d5dd", "hero_description_font": "Inter", "hero_description_size": "18", "info_heading_color": "#ffffff", "info_heading_font": "Manrope", "info_heading_size": "30", "info_description_color": "#e7e5ff", "info_description_font": "Inter", "info_description_size": "16", "form_heading_color": "#111827", "form_heading_font": "Manrope", "form_heading_size": "30", "form_description_color": "#667085", "form_description_font": "Inter", "form_description_size": "16", "support_eyebrow_color": "#e04420", "support_eyebrow_font": "Inter", "support_eyebrow_size": "12", "support_heading_color": "#111827", "support_heading_font": "Manrope", "support_heading_size": "46", "support_description_color": "#667085", "support_description_font": "Inter", "support_description_size": "16", "support_card_title_color": "#111827", "support_card_title_font": "Manrope", "support_card_title_size": "19", "support_card_text_color": "#667085", "support_card_text_font": "Inter", "support_card_text_size": "14", "faq_eyebrow_color": "#e04420", "faq_eyebrow_font": "Inter", "faq_eyebrow_size": "12", "faq_heading_color": "#111827", "faq_heading_font": "Manrope", "faq_heading_size": "46", "faq_description_color": "#667085", "faq_description_font": "Inter", "faq_description_size": "16", "faq_question_color": "#111827", "faq_question_font": "Inter", "faq_question_size": "16", "faq_answer_color": "#667085", "faq_answer_font": "Inter", "faq_answer_size": "16",
        }
        return defaults

    def get(self, request, *args, **kwargs):
        values = self.defaults()
        values.update(Setting.objects.filter(key="contact_page_customization", is_active=True).values_list("value", flat=True).first() or {})
        icons = ["fa-solid fa-envelope", "fa-solid fa-phone", "fa-solid fa-location-dot", "fa-solid fa-box", "fa-solid fa-truck-fast", "fa-solid fa-rotate-left", "fa-solid fa-handshake", "fa-solid fa-headset", "fa-solid fa-circle-question", "fa-solid fa-comments", "fa-solid fa-shield-halved", "fa-solid fa-house", "fa-solid fa-user", "fa-solid fa-users", "fa-solid fa-cart-shopping", "fa-solid fa-bag-shopping", "fa-solid fa-gift", "fa-solid fa-tag", "fa-solid fa-tags", "fa-solid fa-bolt", "fa-solid fa-fire", "fa-solid fa-check", "fa-solid fa-circle-info", "fa-solid fa-lock", "fa-solid fa-star", "fa-solid fa-heart", "fa-solid fa-circle-check", "fa-solid fa-credit-card", "fa-solid fa-wallet", "fa-solid fa-receipt", "fa-solid fa-store", "fa-solid fa-shop", "fa-solid fa-magnifying-glass", "fa-solid fa-arrow-right", "fa-solid fa-chevron-down", "fa-solid fa-calendar", "fa-solid fa-clock", "fa-solid fa-globe", "fa-solid fa-map-pin", "fa-solid fa-image", "fa-solid fa-camera", "fa-solid fa-video", "fa-solid fa-music", "fa-brands fa-facebook", "fa-brands fa-instagram", "fa-brands fa-youtube", "fa-brands fa-linkedin", "fa-brands fa-whatsapp"]
        return render(request, self.template_name, {"settings": values, "fonts": HomePageSettings.FONT_CHOICES, "icons": icons, "sidebar_groups": grouped_modules(), "active_group": "Page Settings", "page_title": "Contact Page Settings"})

    def post(self, request, *args, **kwargs):
        values = {key: request.POST.get(key, "").strip() for key in self.defaults()}
        values["faq_items"] = [{"question": request.POST.get(f"faq_question_{index}", "").strip(), "answer": request.POST.get(f"faq_answer_{index}", "").strip()} for index in range(1, 51) if request.POST.get(f"faq_question_{index}", "").strip() or request.POST.get(f"faq_answer_{index}", "").strip()]
        values["heading_weight"] = request.POST.get("heading_weight", "800")
        values["heading_underline"] = request.POST.get("heading_underline", "none")
        values["body_font_size"] = request.POST.get("body_font_size", "16")
        Setting.objects.update_or_create(key="contact_page_customization", defaults={"value": values, "is_active": True})
        messages.success(request, "Contact page settings saved successfully.")
        if request.POST.get("save_action") == "close":
            return redirect("backoffice:pages")
        return redirect("backoffice:contact-settings")


class BackofficeProductPageSettingsView(SuperAdminRequiredMixin, View):
    template_name = "backoffice/product_page_settings.html"

    def defaults(self):
        defaults = {
            "visit_store_prefix": "Visit the", "reviews_label": "Reviews", "highlight_1": "Verified product data from Nuboxed", "highlight_2": "Store-aware delivery estimate and seller comparison", "highlight_3": "Shop confidently from verified retailers.", "sale_countdown": "Hurry up! Sale ends in:", "delivery_label": "Est. Delivery Time", "add_to_cart": "ADD TO CART", "buy_now": "BUY NOW", "add_wishlist": "Add to Wishlist", "add_compare": "Add to Compare", "share_label": "Share", "policy_1": "Free Shipping & Returns: Available on all orders over $99.", "policy_2": "Estimated Delivery: Orders are typically dispatched within 24 hours.", "policy_3": "Security Policy: Ensuring top-level security for your data and transactions.", "description_tab": "Description", "details_tab": "Product Details", "description_heading": "Its much more than mobile product", "description_fallback": "Shop the most popular featured products.", "description_note": "Your trusted marketplace page, wired to admin product data and structured for fast comparison, clear pricing, and clean buying actions.", "specifications_heading": "PRODUCT DETAILS", "related_heading": "You might also like", "category_heading_suffix": "in the same category:", "comments_heading": "Comments", "grade_label": "Grade", "write_review": "WRITE YOUR REVIEW", "view_all_comments": "View all comments", "customer_voice": "Customer voice", "all_comments": "All comments", "review_modal_heading": "Write your review", "review_title_label": "Title", "review_name_label": "Your name", "review_text_label": "Review", "review_terms": "I agree to the terms and the privacy policy", "required_note": "* Required fields", "cancel_button": "CANCEL", "send_button": "SEND", "review_success": "Thank you. Your review has been submitted successfully.", "quick_brand_fallback": "Store", "quick_delivery": "Est. Delivery Time 2-3 Days", "quick_reviews": "Reviews", "quick_point_1": "Verified product data from Nuboxed", "quick_point_2": "Store-aware delivery estimate and seller comparison", "quick_ram_label": "RAM:", "quick_storage_label": "Internal Storage:", "quick_color_label": "Color:", "quick_add_to_cart": "ADD TO CART", "quick_buy_now": "BUY NOW", "quick_wishlist": "Add to Wishlist", "quick_compare": "Add to Compare", "quick_stock": "Available Stock", "quick_share": "Share", "quick_save_prefix": "Save",
        }
        defaults["show_sale_countdown"] = "1"
        return defaults

    def get(self, request, *args, **kwargs):
        values = self.defaults()
        values.update(Setting.objects.filter(key="product_page_customization", is_active=True).values_list("value", flat=True).first() or {})
        values["policy_1"] = values.get("policy_1", "").replace("$99", "€99")
        values.setdefault("show_share_icons", "1")
        values.setdefault("share_platforms", ["facebook", "x", "linkedin", "pinterest", "email"])
        return render(request, self.template_name, {"settings": values, "sidebar_groups": grouped_modules(), "active_group": "Page Settings", "page_title": "Product Page Settings"})

    def post(self, request, *args, **kwargs):
        values = {key: request.POST.get(key, "").strip() for key in self.defaults()}
        values["show_sale_countdown"] = "1" if request.POST.get("show_sale_countdown") == "1" else "0"
        values["show_share_icons"] = "1" if request.POST.get("show_share_icons") == "1" else "0"
        values["share_platforms"] = [item for item in request.POST.getlist("share_platforms") if item in {"facebook", "x", "linkedin", "pinterest", "email"}]
        Setting.objects.update_or_create(key="product_page_customization", defaults={"value": values, "is_active": True})
        messages.success(request, "Product page settings saved successfully.")
        if request.POST.get("save_action") == "close":
            return redirect("backoffice:pages")
        return redirect("backoffice:product-page-settings")


class BackofficeOrderWorkflowSettingsView(SuperAdminRequiredMixin, TemplateView):
    template_name = "backoffice/order_workflow_settings.html"
    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs)
        global_setting, _ = OrderWorkflowGlobalSetting.objects.get_or_create(key="default")
        stores = Store.objects.filter(retailer__is_active=True).select_related("retailer").order_by("retailer__display_name", "name")
        selected_store_ids = self.request.GET.getlist("store")
        selected_stores = stores.filter(pk__in=selected_store_ids)
        override_rows = []
        for store in selected_stores:
            override = OrderWorkflowStoreOverride.objects.filter(store=store).first()
            override_rows.append((store, OrderWorkflowStoreOverrideForm(instance=override, initial={"is_active": bool(override and override.is_active)})))
        c.update({"page_title": "Order Workflow Settings", "global_form": OrderWorkflowGlobalSettingForm(instance=global_setting), "stores": stores, "selected_store_ids": [str(value) for value in selected_stores.values_list("pk", flat=True)], "workflow_rows": override_rows, "sidebar_groups": grouped_modules(), "module_key_active": None, "active_group": "Commerce"})
        return c
    def post(self, request, *args, **kwargs):
        if request.POST.get("scope") == "global":
            setting, _ = OrderWorkflowGlobalSetting.objects.get_or_create(key="default")
            form = OrderWorkflowGlobalSettingForm(request.POST, instance=setting)
            if form.is_valid():
                form.save(); messages.success(request, "Global order workflow settings saved. All stores now use these defaults.")
        else:
            store = get_object_or_404(Store, pk=request.POST.get("store_id"), retailer__is_active=True)
            override = OrderWorkflowStoreOverride.objects.filter(store=store).first()
            form = OrderWorkflowStoreOverrideForm(request.POST, instance=override)
            if form.is_valid():
                if form.cleaned_data.get("is_active"):
                    saved = form.save(commit=False); saved.store = store; saved.is_active = True; saved.save()
                    messages.success(request, f"Custom workflow saved for {store.name}.")
                elif override:
                    override.delete(); messages.success(request, f"{store.name} now uses the global workflow.")
                else:
                    messages.info(request, f"{store.name} is already using the global workflow.")
            selected_ids = request.POST.getlist("selected_store_ids") or [str(store.pk)]
            return redirect(f"{reverse('backoffice:order-workflow-settings')}?{urlencode([('store', value) for value in selected_ids])}")
        return redirect("backoffice:order-workflow-settings")


class BackofficeEmailSettingsView(SuperAdminRequiredMixin, FormView):
    template_name = "backoffice/email_settings.html"
    form_class = EmailSettingsForm
    success_url = reverse_lazy("backoffice:email-settings")

    def get_current_settings(self):
        return Setting.objects.filter(key="email_settings", is_active=True).values_list("value", flat=True).first() or {}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["current"] = self.get_current_settings()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "page_title": "Email / SMTP Settings",
            "sidebar_groups": grouped_modules(),
            "module_key_active": "email-settings",
            "active_group": "Platform",
        })
        return context

    def form_valid(self, form):
        values = dict(form.cleaned_data)
        current = self.get_current_settings()
        if not values.get("password"):
            values["password"] = current.get("password", "")
        test_recipient = values.pop("test_recipient", "")
        if self.request.POST.get("action") == "test":
            if not test_recipient:
                form.add_error("test_recipient", "Enter an email address to receive the test email.")
                return self.render_to_response(self.get_context_data(form=form))
            try:
                brand = BrandSettings.objects.filter(is_active=True).first()
                send_test_email(test_recipient, values, brand_name=brand.brand_name if brand else "Nuboxed")
            except Exception as exc:
                form.add_error(None, f"Test email failed: {exc}")
                return self.render_to_response(self.get_context_data(form=form))
            messages.success(self.request, f"Test email sent to {test_recipient}.")
            return redirect(self.success_url)
        Setting.objects.update_or_create(key="email_settings", defaults={"value": values, "is_active": True})
        messages.success(self.request, "Email / SMTP settings saved successfully.")
        return super().form_valid(form)


class BackofficeEmailTemplateListView(SuperAdminRequiredMixin, TemplateView):
    template_name = "backoffice/email_templates.html"
    def get_context_data(self, **kwargs):
        ensure_order_email_templates()
        c = super().get_context_data(**kwargs)
        brand = BrandSettings.objects.filter(is_active=True).first()
        brand_name = brand.brand_name if brand else "Nuboxed"
        templates = list(NotificationTemplate.objects.filter(channel=NotificationTemplate.CHANNEL_EMAIL).order_by("event_name"))
        for item in templates:
            if item.subject_template:
                item.subject_template = item.subject_template.replace("CommerceOS", brand_name)
        c.update({"page_title": "Email Templates", "templates": templates, "email_brand_name": brand_name, "sidebar_groups": grouped_modules(), "module_key_active": None, "active_group": "Platform"})
        return c
        return c


class BackofficeEmailTemplateUpdateView(SuperAdminRequiredMixin, UpdateView):
    template_name = "backoffice/email_template_form.html"
    model = NotificationTemplate
    form_class = EmailTemplateForm
    def get_queryset(self): return NotificationTemplate.objects.filter(channel=NotificationTemplate.CHANNEL_EMAIL)
    def get_success_url(self): return reverse("backoffice:email-templates")
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Older seeded templates contain the former product name literally.
        # Show the dynamic placeholder in the editor so the active Brand
        # Settings name is used when the email is sent.
        for field_name in ("subject_template", "body_template"):
            value = form.initial.get(field_name)
            if value and "CommerceOS" in value:
                form.initial[field_name] = value.replace("CommerceOS", "{{ brand_name }}")
        return form
    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs)
        brand = BrandSettings.objects.filter(is_active=True).first()
        c.update({"page_title": "Edit Email Template", "email_brand_name": brand.brand_name if brand else "Nuboxed", "sidebar_groups": grouped_modules(), "module_key_active": None, "active_group": "Platform"})
        return c


class BackofficeNotificationsView(SuperAdminRequiredMixin, TemplateView):
    template_name = "backoffice/notifications.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"page_title": "Notifications", "sidebar_groups": grouped_modules(), "module_key_active": None, "active_group": ""})
        return context


class BackofficeModuleListView(SuperAdminRequiredMixin, RegistryMixin, TemplateView):
    template_name = "backoffice/module_list.html"

    def get(self, request, *args, **kwargs):
        if kwargs.get("module") == "attributes":
            return redirect("backoffice:dashboard")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        module, config = self.get_module_config()
        if module == "brands":
            # Backfill older Device Models brands whenever the Brands page opens.
            for device_brand in PhoneBrand.objects.all():
                sync_device_brand_to_catalog_brand(device_brand)
        queryset = self.get_base_queryset()
        search = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()
        deleted_status = self.request.GET.get("deleted_status", "active").strip()
        trash_field = self.get_trash_field(config["model"])

        # Handle deleted_status filter for soft-deletable catalog modules
        if module == "attributes":
            queryset = ProductAttribute.objects.all()
            if deleted_status == "deleted":
                # Show only deleted attributes
                queryset = queryset.filter(deleted_at__isnull=False)
            elif deleted_status == "all":
                # Show all attributes (deleted and active)
                pass
            else:
                queryset = queryset.filter(deleted_at__isnull=True)
            queryset = queryset.annotate(
                color_priority=Case(
                    When(code="color", then=Value(0)),
                    When(name__iexact="color", then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            ).order_by("color_priority", "name")
        elif module in ("products", "featured-products"):
            if module == "featured-products":
                queryset = Product.objects.filter(is_featured=True)
            else:
                queryset = Product.objects.all()
            queryset = self.filter_trash_queryset(queryset, deleted_status)
            queryset = queryset.order_by("-created_at")
        elif trash_field:
            queryset = config["model"].objects.all().order_by("-created_at")
            if config.get("base_filters"):
                queryset = queryset.filter(**config["base_filters"])
            queryset = self.filter_trash_queryset(queryset, deleted_status)

        if search:
            query = Q()
            for field in config.get("search_fields", []):
                query |= Q(**{f"{field}__icontains": search})
            queryset = queryset.filter(query)

        if status and config.get("status_field"):
            queryset = queryset.filter(**{config["status_field"]: status})

        context.update(
            {
                "module_key": module,
                "module_key_active": module,
                "module_config": config,
                "page_title": config["title"],
                "items": queryset[:50],
                "columns": config["fields"],
                "search": search,
                "status": status,
                "status_field": config.get("status_field"),
                "deleted_status": deleted_status,
                "supports_trash": bool(trash_field),
                "sidebar_groups": self.get_sidebar_groups(),
                "active_group": config["group"],
                "total_count": queryset.count(),
                "create_url": reverse("backoffice:module-create", kwargs={"module": module}),
                "export_url": reverse("backoffice:module-export", kwargs={"module": module}),
            }
        )
        return context


class BackofficeModuleCreateView(SuperAdminRequiredMixin, RegistryMixin, CreateView):
    template_name = "backoffice/module_form.html"

    def get_template_names(self):
        module = self.kwargs.get("module")
        if module == "products":
            return ["backoffice/product_form.html"]
        if module == "stores":
            return ["backoffice/store_form.html"]
        return [self.template_name]

    def get_form_class(self):
        return self.get_module_form_class()

    def get_success_url(self):
        if (
            self.request.method == "POST"
            and self.request.POST.get("save_action", "stay") == "stay"
            and getattr(self, "object", None)
        ):
            return reverse("backoffice:module-edit", kwargs={"module": self.kwargs["module"], "pk": self.object.pk})
        if self.kwargs["module"] == "attributes" and getattr(self, "object", None):
            return reverse("backoffice:attribute-options", kwargs={"pk": self.object.pk})
        return reverse("backoffice:module-list", kwargs={"module": self.kwargs["module"]})

    def form_valid(self, form):
        if self.kwargs.get("module") == "stores" and "status" in form.cleaned_data:
            form.instance.status = form.cleaned_data["status"]
            form.instance.is_active = form.instance.status == Store.STATUS_ACTIVE
        # Process any library file assignments before saving the form
        for field_name in form.fields:
            lib_id = self.request.POST.get(f"{field_name}_library_id")
            if lib_id:
                try:
                    from apps.catalog.models import MediaLibrary
                    asset = MediaLibrary.objects.get(id=lib_id)
                    setattr(form.instance, field_name, asset.file)
                except Exception:
                    pass
        module = self.kwargs["module"]
        if module in ("products", "featured-products"):
            from apps.catalog.services import unique_sku
            from apps.catalog.views import ProductAssetSyncMixin
            from apps.stores.models import Store

            product = form.save(commit=False)
            if not getattr(product, "store_id", None):
                product.store = Store.objects.order_by("-is_active", "-updated_at").first()
            if product.store and not getattr(product, "retailer_id", None):
                product.retailer = product.store.retailer
            if not product.sku:
                product.sku = unique_sku(Product, product.name)
            product.status = Product.STATUS_APPROVED
            product.is_active = True
            product.save()
            self.object = product
            sync_product_amazon_mapping(product, form.cleaned_data.get("amazon_seller_sku"), form.cleaned_data.get("amazon_asin"))
            form.save_product_attributes(product)
            form.sync_product_variants(product)
            sync_mixin = ProductAssetSyncMixin()
            sync_mixin.request = self.request
            sync_mixin.sync_product_assets(product, form)
            sync_mixin.sync_default_variant(product, form)
            messages.success(self.request, "Product created successfully.")
            return redirect(self.get_success_url())

        response = super().form_valid(form)
        if module == "attributes":
            self.save_color_values(self.object, form.cleaned_data.get("color_values_payload"))
        if module == "products":
            messages.success(self.request, "Product created successfully.")
        return response

    def form_invalid(self, form):
        if self.kwargs.get("module") == "products":
            messages.error(self.request, "Product could not be created. Please check the highlighted fields.")
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        module, config = self.get_module_config()

        # Add product-specific context
        if module == "products":
            from apps.catalog.views import ProductAssetSyncMixin
            from apps.catalog.models import Category, Brand, PhoneBrand, PhoneModel, PhoneModelVariant, PhonePlatform, PhoneStorageOption, PhoneColorOption, PhoneRamOption
            from apps.retailers.models import Retailer
            from apps.stores.models import Store
            normalize_comma_separated_phone_models()
            platforms = PhonePlatform.objects.all().order_by("name")
            brands = PhoneBrand.objects.select_related("platform").order_by("platform__name", "sort_order", "name")
            models = PhoneModel.objects.select_related("platform", "brand").filter(is_active=True).order_by("platform__name", "brand__name", "sort_order", "name")
            variants = PhoneModelVariant.objects.select_related("phone_model", "phone_model__brand").order_by("phone_model__name", "sort_order", "storage", "color")
            storages = PhoneStorageOption.objects.filter(is_active=True).order_by("sort_order", "label")
            colors = PhoneColorOption.objects.filter(is_active=True).order_by("sort_order", "name")
            rams = PhoneRamOption.objects.filter(is_active=True).order_by("sort_order", "label")
            context.update({
                "categories": Category.objects.all().order_by("name"),
                "brands": Brand.objects.all().order_by("name"),
                "retailers": Retailer.objects.all().order_by("legal_name", "display_name"),
                "stores": Store.objects.all().order_by("name"),
                "product_assets": [],
                "external_video_rows_json": ProductAssetSyncMixin().get_external_video_rows_json(),
                "all_platforms": platforms,
                "all_phone_brands": brands,
                "all_phone_models": models,
                "all_phone_variants": variants,
                "phone_picker_payload": json.dumps(
                    {
                        "platforms": [{"id": str(item.id), "name": item.name, "label": item.get_name_display()} for item in platforms],
                        "brands": [
                            {
                                "id": str(item.id),
                                "name": item.name,
                                "label": item.name,
                                "platform_id": str(item.platform_id),
                                "platform_name": item.platform.name,
                            }
                            for item in brands
                        ],
                        "models": [
                            {
                                "id": str(item.id),
                                "name": item.name,
                                "display_name": item.display_name,
                                "platform_id": str(item.platform_id),
                                "platform_name": item.platform.name,
                                "brand_id": str(item.brand_id) if item.brand_id else "",
                            }
                            for item in models
                        ],
                        "variants": [
                            {
                                "id": str(item.id),
                                "label": item.display_name,
                                "phone_model_id": str(item.phone_model_id),
                                "ram": item.ram,
                                "storage": item.storage,
                                "color": item.color,
                                "color_hex": item.color_hex,
                            }
                            for item in variants
                        ],
                        "storages": [{"id": item.label, "label": item.label} for item in storages],
                        "colors": [{"id": item.name, "label": item.name, "color_hex": item.color_hex} for item in colors],
                        "rams": [{"id": item.label, "label": item.label} for item in rams],
                    }
                ),
                "selected_phone_variant_id": str(getattr(context["form"].instance, "phone_variant_id", "") or ""),
            })

        context.update(
            {
                "page_title": f"Create {config['title'][:-1] if config['title'].endswith('s') else config['title']}",
                "module_config": config,
                "sidebar_groups": self.get_sidebar_groups(),
                "module_key_active": module,
                "active_group": config["group"],
                "cancel_url": self.get_success_url(),
                "show_color_manager": False,
                "color_value_rows_json": "[]",
                "manage_options_url": None,
                "product_attribute_fields": [],
            }
        )
        return context


class BackofficeModuleUpdateView(SuperAdminRequiredMixin, RegistryMixin, UpdateView):
    template_name = "backoffice/module_form.html"

    def get_template_names(self):
        module = self.kwargs.get("module")
        if module == "products":
            return ["backoffice/product_form.html"]
        if module == "stores":
            return ["backoffice/store_form.html"]
        return [self.template_name]

    def get_queryset(self):
        return self.get_base_queryset()

    def get_form_class(self):
        return self.get_module_form_class()

    def get_success_url(self):
        if (
            self.request.method == "POST"
            and self.request.POST.get("save_action", "stay") == "stay"
            and getattr(self, "object", None)
        ):
            return reverse("backoffice:module-edit", kwargs={"module": self.kwargs["module"], "pk": self.object.pk})
        return reverse("backoffice:module-list", kwargs={"module": self.kwargs["module"]})

    def form_valid(self, form):
        if self.kwargs.get("module") == "stores" and "status" in form.cleaned_data:
            form.instance.status = form.cleaned_data["status"]
            form.instance.is_active = form.instance.status == Store.STATUS_ACTIVE
        # Process any library file assignments before saving the form
        for field_name in form.fields:
            lib_id = self.request.POST.get(f"{field_name}_library_id")
            if lib_id:
                try:
                    from apps.catalog.models import MediaLibrary
                    asset = MediaLibrary.objects.get(id=lib_id)
                    setattr(form.instance, field_name, asset.file)
                except Exception:
                    pass
        response = super().form_valid(form)
        module = self.kwargs["module"]
        if module == "attributes":
            self.save_color_values(self.object, form.cleaned_data.get("color_values_payload"))
        elif module in ("products", "featured-products"):
            sync_product_amazon_mapping(self.object, form.cleaned_data.get("amazon_seller_sku"), form.cleaned_data.get("amazon_asin"))
            from apps.catalog.views import ProductAssetSyncMixin
            sync_mixin = ProductAssetSyncMixin()
            sync_mixin.request = self.request
            form.save_product_attributes(self.object)
            form.sync_product_variants(self.object)
            sync_mixin.sync_product_assets(self.object, form)
            sync_mixin.sync_default_variant(self.object, form)
            self.object.phone_variant = form.resolve_phone_variant_from_payload()
            self.object.sync_phone_identity()
            self.object.save(update_fields=["phone_variant", "model_name", "name", "updated_at"])
        if module == "products":
            messages.success(self.request, "Product updated successfully.")
        return response

    def form_invalid(self, form):
        if self.kwargs.get("module") == "products":
            messages.error(self.request, "Product could not be updated. Please check the highlighted fields.")
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        module, config = self.get_module_config()

        # Add product-specific context
        if module == "products":
            from apps.catalog.views import ProductAssetSyncMixin
            from apps.catalog.models import Category, Brand, PhoneBrand, PhoneModel, PhoneModelVariant, PhonePlatform, PhoneStorageOption, PhoneColorOption, PhoneRamOption
            from apps.retailers.models import Retailer
            from apps.stores.models import Store
            normalize_comma_separated_phone_models()
            platforms = PhonePlatform.objects.all().order_by("name")
            brands = PhoneBrand.objects.select_related("platform").order_by("platform__name", "sort_order", "name")
            models = PhoneModel.objects.select_related("platform", "brand").filter(is_active=True).order_by("platform__name", "brand__name", "sort_order", "name")
            variants = PhoneModelVariant.objects.select_related("phone_model", "phone_model__brand").order_by("phone_model__name", "sort_order", "storage", "color")
            storages = PhoneStorageOption.objects.filter(is_active=True).order_by("sort_order", "label")
            colors = PhoneColorOption.objects.filter(is_active=True).order_by("sort_order", "name")
            rams = PhoneRamOption.objects.filter(is_active=True).order_by("sort_order", "label")
            context.update({
                "categories": Category.objects.all().order_by("name"),
                "brands": Brand.objects.all().order_by("name"),
                "retailers": Retailer.objects.all().order_by("legal_name", "display_name"),
                "stores": Store.objects.all().order_by("name"),
                "product_assets": self.object.media_items.all().order_by("sort_order", "-is_primary") if getattr(self, "object", None) else [],
                "external_video_rows_json": ProductAssetSyncMixin().get_external_video_rows_json(self.object if getattr(self, "object", None) else None),
                "all_platforms": platforms,
                "all_phone_brands": brands,
                "all_phone_models": models,
                "all_phone_variants": variants,
                "phone_picker_payload": json.dumps(
                    {
                        "platforms": [{"id": str(item.id), "name": item.name, "label": item.get_name_display()} for item in platforms],
                        "brands": [
                            {
                                "id": str(item.id),
                                "name": item.name,
                                "label": item.name,
                                "platform_id": str(item.platform_id),
                                "platform_name": item.platform.name,
                            }
                            for item in brands
                        ],
                        "models": [
                            {
                                "id": str(item.id),
                                "name": item.name,
                                "display_name": item.display_name,
                                "platform_id": str(item.platform_id),
                                "platform_name": item.platform.name,
                                "brand_id": str(item.brand_id) if item.brand_id else "",
                            }
                            for item in models
                        ],
                        "variants": [
                            {
                                "id": str(item.id),
                                "label": item.display_name,
                                "phone_model_id": str(item.phone_model_id),
                                "ram": item.ram,
                                "storage": item.storage,
                                "color": item.color,
                                "color_hex": item.color_hex,
                            }
                            for item in variants
                        ],
                        "storages": [{"id": item.label, "label": item.label} for item in storages],
                        "colors": [{"id": item.name, "label": item.name, "color_hex": item.color_hex} for item in colors],
                        "rams": [{"id": item.label, "label": item.label} for item in rams],
                    }
                ),
                "selected_phone_variant_id": str(getattr(context["form"].instance, "phone_variant_id", "") or ""),
            })

        context.update(
            {
                "page_title": f"Edit {config['title'][:-1] if config['title'].endswith('s') else config['title']}",
                "module_config": config,
                "sidebar_groups": self.get_sidebar_groups(),
                "module_key_active": module,
                "active_group": config["group"],
                "cancel_url": self.get_success_url(),
                "show_color_manager": False,
                "color_value_rows_json": "[]",
                "manage_options_url": None,
                "product_attribute_fields": [
                    context["form"][field_name]
                    for field_name in getattr(context["form"], "dynamic_attribute_field_names", [])
                ],
            }
        )
        return context


class BackofficeAttributeOptionsView(SuperAdminRequiredMixin, FormView):
    template_name = "backoffice/attribute_options.html"
    form_class = BackofficeAttributeOptionsForm

    def get_attribute(self):
        return ProductAttribute.objects.get(pk=self.kwargs["pk"])

    def get_success_url(self):
        return reverse("backoffice:attribute-options", kwargs={"pk": self.kwargs["pk"]})

    def form_valid(self, form):
        self.save_color_values(self.get_attribute(), form.cleaned_data.get("options_payload"))
        return super().form_valid(form)

    def save_color_values(self, attribute, payload):
        RegistryMixin.save_color_values(self, attribute, payload)

    def get_color_value_rows(self, attribute):
        return RegistryMixin.get_color_value_rows(self, attribute)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        attribute = self.get_attribute()
        context.update(
            {
                "page_title": f"{attribute.name} Options",
                "attribute": attribute,
                "sidebar_groups": grouped_modules(),
                "module_key_active": "attributes",
                "active_group": "Catalog",
                "cancel_url": reverse("backoffice:module-list", kwargs={"module": "attributes"}),
                "options_rows_json": json.dumps(self.get_color_value_rows(attribute)),
            }
        )
        return context


class BackofficeExportView(SuperAdminRequiredMixin, RegistryMixin, TemplateView):
    def get(self, request, *args, **kwargs):
        module, config = self.get_module_config()
        queryset = self.get_base_queryset()
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{module}.csv"'
        writer = csv.writer(response)
        writer.writerow(config["fields"])
        for item in queryset:
            writer.writerow([getattr(item, field) for field in config["fields"]])
        return response


class BackofficeAttributeDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        try:
            attribute = ProductAttribute.objects.get(pk=pk, deleted_at__isnull=True)
            attribute.deleted_at = timezone.now()
            attribute.save()
            return JsonResponse({"success": True, "message": "✓ Attribute deleted successfully"})
        except ProductAttribute.DoesNotExist:
            return JsonResponse({"success": False, "message": "Attribute not found"}, status=404)
        except Exception as e:
            return JsonResponse({"success": False, "message": f"Error: {str(e)}"}, status=500)


class BackofficeAttributeRestoreView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        try:
            attribute = ProductAttribute.objects.get(pk=pk, deleted_at__isnull=False)
            attribute.deleted_at = None
            attribute.save()
            return JsonResponse({"success": True, "message": "✓ Attribute restored successfully"})
        except ProductAttribute.DoesNotExist:
            return JsonResponse({"success": False, "message": "Attribute not found or not deleted"}, status=404)
        except Exception as e:
            return JsonResponse({"success": False, "message": f"Error: {str(e)}"}, status=500)


class BackofficeAttributePermanentDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        try:
            attribute = ProductAttribute.objects.get(pk=pk)
            attribute.delete()
            return JsonResponse({"success": True, "message": "✓ Attribute permanently deleted"})
        except ProductAttribute.DoesNotExist:
            return JsonResponse({"success": False, "message": "Attribute not found"}, status=404)
        except Exception as e:
            return JsonResponse({"success": False, "message": f"Error: {str(e)}"}, status=500)


class BackofficeProductDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        try:
            product = Product.objects.get(pk=pk, deleted_at__isnull=True)
            product.deleted_at = timezone.now()
            product.is_active = False
            product.save(update_fields=["deleted_at", "is_active", "updated_at"])
            return JsonResponse({"success": True, "message": "✓ Product deleted successfully"})
        except Product.DoesNotExist:
            return JsonResponse({"success": False, "message": "Product not found"}, status=404)
        except Exception as e:
            return JsonResponse({"success": False, "message": f"Error: {str(e)}"}, status=500)


class BackofficeProductRestoreView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        try:
            product = Product.objects.get(pk=pk, deleted_at__isnull=False)
            product.deleted_at = None
            product.is_active = True
            product.save(update_fields=["deleted_at", "is_active", "updated_at"])
            return JsonResponse({"success": True, "message": "✓ Product restored successfully"})
        except Product.DoesNotExist:
            return JsonResponse({"success": False, "message": "Product not found or not deleted"}, status=404)
        except Exception as e:
            return JsonResponse({"success": False, "message": f"Error: {str(e)}"}, status=500)


class BackofficeProductPermanentDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        try:
            product = Product.objects.get(pk=pk)
            product.delete()
            return JsonResponse({"success": True, "message": "✓ Product permanently deleted"})
        except Product.DoesNotExist:
            return JsonResponse({"success": False, "message": "Product not found"}, status=404)
        except Exception as e:
            return JsonResponse({"success": False, "message": f"Error: {str(e)}"}, status=500)


class BackofficeModuleTrashActionView(SuperAdminRequiredMixin, RegistryMixin, View):
    action = None

    def post(self, request, module, pk):
        try:
            if self.action not in {"delete", "restore", "delete-permanent"}:
                raise Http404("Invalid trash action.")
            model = MODULES[module]["model"]
            obj = model.objects.get(pk=pk)
            label = MODULES[module]["title"].rstrip("s")

            if self.action == "delete":
                self.soft_delete_object(obj)
                return JsonResponse({"success": True, "message": f"✓ {label} moved to trash"})
            if self.action == "restore":
                self.restore_object(obj)
                return JsonResponse({"success": True, "message": f"✓ {label} restored"})

            obj.delete()
            return JsonResponse({"success": True, "message": f"✓ {label} permanently deleted"})
        except KeyError:
            return JsonResponse({"success": False, "message": "Unknown module"}, status=404)
        except ValueError as e:
            return JsonResponse({"success": False, "message": str(e)}, status=400)
        except Exception as e:
            if "DoesNotExist" in type(e).__name__:
                return JsonResponse({"success": False, "message": "Item not found"}, status=404)
            return JsonResponse({"success": False, "message": f"Error: {str(e)}"}, status=500)


class BackofficeModuleDeleteView(BackofficeModuleTrashActionView):
    action = "delete"


class BackofficeModuleRestoreView(BackofficeModuleTrashActionView):
    action = "restore"


class BackofficeModulePermanentDeleteView(BackofficeModuleTrashActionView):
    action = "delete-permanent"


class BackofficeVariantDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        from apps.catalog.models import ProductVariant
        try:
            variant = ProductVariant.objects.get(pk=pk, deleted_at__isnull=True)
            variant.deleted_at = timezone.now()
            variant.save()
            return JsonResponse({"success": True, "message": "✓ Variant deleted successfully"})
        except ProductVariant.DoesNotExist:
            return JsonResponse({"success": False, "message": "Variant not found"}, status=404)
        except Exception as e:
            return JsonResponse({"success": False, "message": f"Error: {str(e)}"}, status=500)


class BackofficeVariantRestoreView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        from apps.catalog.models import ProductVariant
        try:
            variant = ProductVariant.objects.get(pk=pk, deleted_at__isnull=False)
            variant.deleted_at = None
            variant.save()
            return JsonResponse({"success": True, "message": "✓ Variant restored successfully"})
        except ProductVariant.DoesNotExist:
            return JsonResponse({"success": False, "message": "Variant not found or not deleted"}, status=404)
        except Exception as e:
            return JsonResponse({"success": False, "message": f"Error: {str(e)}"}, status=500)


class BackofficeVariantPermanentDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        from apps.catalog.models import ProductVariant
        try:
            variant = ProductVariant.objects.get(pk=pk)
            variant.delete()
            return JsonResponse({"success": True, "message": "✓ Variant permanently deleted"})
        except ProductVariant.DoesNotExist:
            return JsonResponse({"success": False, "message": "Variant not found"}, status=404)
        except Exception as e:
            return JsonResponse({"success": False, "message": f"Error: {str(e)}"}, status=500)


class BackofficeProductVariantsView(SuperAdminRequiredMixin, RegistryMixin, TemplateView):
    template_name = "backoffice/product_variants.html"

    def get(self, request, *args, **kwargs):
        return redirect("backoffice:phone-models")

    def get_context_data(self, **kwargs):
        from apps.catalog.models import Product, ProductVariant
        from apps.inventory.models import StockItem, StockLedger

        context = super().get_context_data(**kwargs)
        page_title = "Device Models"

        # Get all variants (active and deleted)
        variants = ProductVariant.objects.select_related("product").order_by("-created_at")

        # Prepare variant data for template
        variants_data = []
        for variant in variants:
            variants_data.append({
                "variant": variant,
            })

        context.update({
            "page_title": page_title,
            "variants": variants_data,
            "sidebar_groups": self.get_sidebar_groups(),
            "active_group": "Catalog",
            "module_key_active": "device-models",
        })
        return context


class BackofficeProductVariantCreateView(SuperAdminRequiredMixin, RegistryMixin, TemplateView):
    template_name = "backoffice/product_variant_create.html"

    def get(self, request, *args, **kwargs):
        return redirect("backoffice:phone-models")

    def get_context_data(self, **kwargs):
        from apps.catalog.models import Product, ProductAttribute

        context = super().get_context_data(**kwargs)
        context.update({
            "page_title": "Create Product Variant",
            "products": Product.objects.filter(product_type=Product.TYPE_VARIANT).order_by("name"),
            "sidebar_groups": self.get_sidebar_groups(),
            "active_group": "Catalog",
            "module_key_active": "device-models",
        })
        return context

    def post(self, request, *args, **kwargs):
        from apps.catalog.models import Product, ProductVariant
        import json
        import uuid

        try:
            data = json.loads(request.body)
            product_ids = data.get("product_ids", [])
            variant_name = data.get("variant_name", "").strip()

            # Validate
            if not product_ids or len(product_ids) == 0:
                return JsonResponse({
                    "success": False,
                    "message": "Select at least one product",
                }, status=400)

            if not variant_name:
                return JsonResponse({
                    "success": False,
                    "message": "Variant name is required",
                }, status=400)

            created_count = 0
            created_variants = []

            # Create variant for each selected product
            for product_id in product_ids:
                try:
                    product = Product.objects.get(id=product_id, product_type=Product.TYPE_VARIANT)
                except Product.DoesNotExist:
                    continue

                # Generate unique SKU
                base_sku = f"{product.sku}-{variant_name[:3].upper()}"
                sku = f"{base_sku}-{uuid.uuid4().hex[:4].upper()}"

                # Create variant
                variant = ProductVariant.objects.create(
                    product=product,
                    name=variant_name,
                    sku=sku,
                    price=product.price,
                    is_default=False,
                )

                created_variants.append({
                    "id": str(variant.id),
                    "name": variant.name,
                    "sku": variant.sku,
                    "product": product.name,
                })
                created_count += 1

            if created_count == 0:
                return JsonResponse({
                    "success": False,
                    "message": "No valid products found",
                }, status=400)

            return JsonResponse({
                "success": True,
                "message": f"✓ Created {created_count} variant(s) successfully",
                "variants": created_variants,
            })
        except Exception as e:
            return JsonResponse({
                "success": False,
                "message": f"Error: {str(e)}",
            }, status=400)


class ProductAttributesAPIView(SuperAdminRequiredMixin, View):
    def get(self, request, product_id):
        from apps.catalog.models import Product, ProductAttribute, ProductAttributeOption

        try:
            product = Product.objects.get(id=product_id)

            # Get variant attributes
            attributes = ProductAttribute.objects.filter(
                deleted_at__isnull=True,
                is_variant_attribute=True
            ).order_by("name")

            result = {}

            for attr in attributes:
                options = attr.options.values_list("value", flat=True)
                attr_key = attr.code.lower()

                if options:
                    result[attr_key] = [{"value": opt} for opt in options]

            return JsonResponse({
                "colors": result.get("color", []),
                "sizes": result.get("size", []),
                "custom": [v for k, v in result.items() if k not in ["color", "size"] for item in v],
            })
        except Product.DoesNotExist:
            return JsonResponse({"error": "Product not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


class SliderProductsAPIView(SuperAdminRequiredMixin, View):
    """Return approved products only after a retailer is selected in slider editor."""
    def get(self, request):
        retailer_id = request.GET.get("retailer_id")
        if not retailer_id:
            return JsonResponse({"products": []})
        products = Product.objects.filter(
            retailer_id=retailer_id,
            is_active=True,
            status=Product.STATUS_APPROVED,
        ).order_by("name")
        return JsonResponse({
            "products": [
                {"id": str(product.id), "label": f"{product.name} · {product.sku}"}
                for product in products
            ]
        })

# ─── Phone Model Management Views ─────────────────────────────────────────────

class PhoneModelsView(SuperAdminRequiredMixin, RegistryMixin, TemplateView):
    """Main listing page: all device families, brands, models and variants."""
    template_name = "backoffice/phone_models.html"

    def get_management_models(self, queryset):
        models = list(queryset)
        grouped_names = {}
        for model in models:
            names = split_comma_values(model.name)
            if len(names) > 1:
                grouped_names.setdefault((model.platform_id, model.brand_id), set()).update(name.lower() for name in names)
        return [
            model for model in models
            if "," in model.name or model.name.lower() not in grouped_names.get((model.platform_id, model.brand_id), set())
        ]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        normalize_comma_separated_phone_models()
        platforms = PhonePlatform.objects.prefetch_related(
            "brands",
            "models",
            "models__brand",
            "models__variants",
        ).all().order_by("name")
        for platform in platforms:
            platform.active_brands = platform.brands.filter(is_active=True).order_by("sort_order", "name")
            platform.deleted_brands = platform.brands.filter(is_active=False).order_by("sort_order", "name")
            platform.active_models = self.get_management_models(platform.models.filter(is_active=True).select_related("brand").order_by("sort_order", "name"))
            platform.deleted_models = self.get_management_models(platform.models.filter(is_active=False).select_related("brand").order_by("sort_order", "name"))
            for brand in list(platform.active_brands) + list(platform.deleted_brands):
                brand.active_models = self.get_management_models(brand.models.filter(is_active=True).order_by("sort_order", "name"))
                brand.deleted_models = self.get_management_models(brand.models.filter(is_active=False).order_by("sort_order", "name"))
            for model in list(platform.active_models) + list(platform.deleted_models):
                model.active_variants = model.variants.filter(is_active=True).order_by("sort_order", "storage", "color")
                model.deleted_variants = model.variants.filter(is_active=False).order_by("sort_order", "storage", "color")
            platform.variants_count = sum(model.active_variants.count() for model in platform.active_models)
        ram_options = PhoneRamOption.objects.order_by("-is_active", "sort_order", "label")
        storage_options = PhoneStorageOption.objects.order_by("-is_active", "sort_order", "label")
        colour_options = PhoneColorOption.objects.order_by("-is_active", "sort_order", "name")
        ram_presets = self.get_ram_presets()
        storage_presets = self.get_storage_presets()
        colour_name_presets = self.get_colour_name_presets()
        colour_presets = self.get_colour_presets()
        ctx["platforms"] = platforms
        ctx["ram_options"] = ram_options
        ctx["storage_options"] = storage_options
        ctx["colour_options"] = colour_options
        ctx["ram_capacity_presets"] = ram_presets
        ctx["storage_capacity_presets"] = storage_presets
        ctx["colour_name_presets"] = colour_name_presets
        ctx["colour_presets"] = colour_presets
        ctx["page_title"] = "Device Models"
        ctx["sidebar_groups"] = self.get_sidebar_groups()
        ctx["active_group"] = "Catalog"
        ctx["module_key_active"] = "device-models"
        return ctx

    def get_ram_presets(self):
        labels = []
        seen = set()
        from apps.catalog.models import PhoneRamOption
        for option in PhoneRamOption.objects.filter(is_active=True).order_by("sort_order", "label"):
            key = option.label.strip().lower()
            if key and key not in seen:
                seen.add(key)
                labels.append(option.label)
        for value in self.get_distinct_variant_values("ram"):
            key = value.strip().lower()
            if key and key not in seen:
                seen.add(key)
                labels.append(value)
        return labels

    def get_storage_presets(self):
        labels = []
        seen = set()
        for option in PhoneStorageOption.objects.filter(is_active=True).order_by("sort_order", "label"):
            key = option.label.strip().lower()
            if key and key not in seen:
                seen.add(key)
                labels.append(option.label)
        for value in self.get_distinct_variant_values("storage"):
            key = value.strip().lower()
            if key and key not in seen:
                seen.add(key)
                labels.append(value)
        return labels

    def get_colour_name_presets(self):
        names = []
        seen = set()
        for option in PhoneColorOption.objects.filter(is_active=True).order_by("sort_order", "name"):
            key = option.name.strip().lower()
            if key and key not in seen:
                seen.add(key)
                names.append(option.name)
        for value in self.get_distinct_variant_values("color"):
            key = value.strip().lower()
            if key and key not in seen:
                seen.add(key)
                names.append(value)
        return names

    def get_distinct_variant_values(self, field_name):
        values = (
            PhoneModelVariant.objects.filter(is_active=True)
            .exclude(**{field_name: ""})
            .order_by(field_name)
            .values_list(field_name, flat=True)
            .distinct()
        )
        return [value for value in values if value]

    def get_colour_presets(self):
        presets = []
        seen = set()
        color_options = list(
            PhoneColorOption.objects.filter(is_active=True)
            .order_by("sort_order", "name")
            .values("name", "color_hex")
        )
        color_options.extend(
            {
                "name": variant["color"],
                "color_hex": variant["color_hex"],
            }
            for variant in PhoneModelVariant.objects.filter(is_active=True)
            .exclude(color="")
            .order_by("color", "color_hex")
            .values("color", "color_hex")
        )
        for option in color_options:
            name = (option["name"] or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            presets.append({"name": name, "hex": (option["color_hex"] or "").strip()})
        return presets


class DeviceCatalogPresetSyncView(SuperAdminRequiredMixin, View):
    """Add the maintained device catalogue without touching admin-created data."""

    def post(self, request):
        stats = seed_device_catalog()
        stats.update(rebuild_device_options_and_variants())
        return JsonResponse({"success": True, **stats})


class PhonePlatformCreateView(SuperAdminRequiredMixin, View):
    """POST only – create a platform (Apple / Android)."""
    def post(self, request):
        name = request.POST.get("name", "").strip()
        if not name:
            return JsonResponse({"error": "Name is required"}, status=400)
        if name not in dict(PhonePlatform.PLATFORM_CHOICES):
            return JsonResponse({"error": "Invalid platform"}, status=400)
        obj, created = PhonePlatform.objects.get_or_create(name=name)
        return JsonResponse({"id": str(obj.id), "name": obj.get_name_display(), "created": created})


class PhonePlatformDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        platform = get_object_or_404(PhonePlatform, id=pk)
        platform.is_active = False
        platform.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"success": True, "status": "deleted"})


class PhonePlatformRestoreView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        platform = get_object_or_404(PhonePlatform, id=pk)
        platform.is_active = True
        platform.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"success": True, "status": "restored"})


class PhonePlatformPermanentDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        platform = get_object_or_404(PhonePlatform, id=pk, is_active=False)
        platform.delete()
        return JsonResponse({"success": True, "status": "deleted-permanent"})


class PhoneBrandCreateView(SuperAdminRequiredMixin, View):
    def post(self, request):
        from django.utils.text import slugify
        name = request.POST.get("name", "").strip()
        platform_id = request.POST.get("platform_id", "").strip()
        if not name or not platform_id:
            return JsonResponse({"error": "name and platform_id are required"}, status=400)
        platform = get_object_or_404(PhonePlatform, id=platform_id)
        slug = slugify(name)
        counter = 1
        base_slug = slug
        while PhoneBrand.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        obj = PhoneBrand.objects.create(platform=platform, name=name, slug=slug)
        sync_device_brand_to_catalog_brand(obj)
        return JsonResponse({"id": str(obj.id), "name": obj.name, "platform_id": str(platform.id)})


class PhoneBrandUpdateView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        brand = get_object_or_404(PhoneBrand, id=pk)
        name = request.POST.get("name", "").strip()
        if name:
            previous_name = brand.name
            brand.name = name
            brand.save(update_fields=["name", "updated_at"])
            sync_device_brand_to_catalog_brand(brand, previous_name=previous_name)
        return JsonResponse({"id": str(brand.id), "name": brand.name})


class PhoneBrandDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        brand = get_object_or_404(PhoneBrand, id=pk)
        brand.is_active = False
        brand.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"success": True, "status": "deleted"})


class PhoneBrandRestoreView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        brand = get_object_or_404(PhoneBrand, id=pk)
        brand.is_active = True
        brand.save(update_fields=["is_active", "updated_at"])
        sync_device_brand_to_catalog_brand(brand)
        return JsonResponse({"success": True, "status": "restored"})


class PhoneBrandPermanentDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        brand = get_object_or_404(PhoneBrand, id=pk, is_active=False)
        brand.delete()
        return JsonResponse({"success": True, "status": "deleted-permanent"})


class PhoneModelCreateView(SuperAdminRequiredMixin, View):
    def post(self, request):
        raw_name = request.POST.get("name", "").strip()
        platform_id = request.POST.get("platform_id", "").strip()
        brand_id = request.POST.get("brand_id", "").strip()
        released_year = request.POST.get("released_year", "").strip() or None

        model_names = split_comma_values(raw_name)

        if not model_names or not platform_id:
            return JsonResponse({"error": "name and platform_id are required"}, status=400)

        platform = get_object_or_404(PhonePlatform, id=platform_id)
        brand = None
        if brand_id:
            brand = get_object_or_404(PhoneBrand, id=brand_id, platform=platform)

        year_value = None
        if released_year:
            try:
                year_value = int(released_year)
            except ValueError:
                year_value = None

        display_name = raw_name if len(model_names) > 1 else model_names[0]
        obj = (
            PhoneModel.objects.filter(
                platform=platform,
                brand=brand,
                name__iexact=display_name,
            )
            .order_by("-is_active", "sort_order", "name")
            .first()
        )
        created = False
        if obj is None:
            obj = PhoneModel(platform=platform, brand=brand, name=display_name)
            created = True
        else:
            obj.name = display_name
            if not obj.is_active:
                obj.is_active = True
        if year_value:
            obj.released_year = year_value
        obj.save()
        split_models = sync_split_phone_models_from_combined(obj) if len(model_names) > 1 else []
        return JsonResponse({
            "id": str(obj.id),
            "name": obj.name,
            "display_name": obj.display_name,
            "platform_id": str(platform.id),
            "brand_id": str(brand.id) if brand else None,
            "created": created,
            "created_count": 1,
            "models": [
                {
                    "id": str(obj.id),
                    "name": obj.name,
                    "display_name": obj.display_name,
                    "platform_id": str(platform.id),
                    "brand_id": str(brand.id) if brand else None,
                    "created": created,
                }
            ],
            "split_count": len(split_models),
        })


class PhoneModelUpdateView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(PhoneModel, id=pk)
        previous_names = split_comma_values(obj.name)
        name = request.POST.get("name", "").strip()
        platform_id = request.POST.get("platform_id", "").strip()
        brand_id = request.POST.get("brand_id", "").strip()
        released_year = request.POST.get("released_year", "").strip() or None
        if name:
            obj.name = name
        if platform_id:
            obj.platform = get_object_or_404(PhonePlatform, id=platform_id)
        obj.brand = get_object_or_404(PhoneBrand, id=brand_id, platform=obj.platform) if brand_id else None
        if released_year:
            try:
                obj.released_year = int(released_year)
            except ValueError:
                pass
        obj.save(update_fields=["platform", "brand", "name", "released_year", "updated_at"])
        sync_split_phone_models_from_combined(obj, previous_names=previous_names)
        return JsonResponse({"id": str(obj.id), "display_name": obj.display_name})


class PhoneModelDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(PhoneModel, id=pk)
        obj.is_active = False
        obj.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"success": True, "status": "deleted"})


class PhoneModelRestoreView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(PhoneModel, id=pk)
        obj.is_active = True
        obj.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"success": True, "status": "restored"})


class PhoneModelPermanentDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(PhoneModel, id=pk, is_active=False)
        obj.delete()
        return JsonResponse({"success": True, "status": "deleted-permanent"})


class PhoneStorageOptionCreateView(SuperAdminRequiredMixin, View):
    def post(self, request):
        label = request.POST.get("label", "").strip()
        if not label:
            return JsonResponse({"error": "Storage capacity is required"}, status=400)
        obj, created = PhoneStorageOption.objects.get_or_create(label=label)
        if not obj.is_active:
            obj.is_active = True
            obj.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"id": str(obj.id), "label": obj.label, "created": created})


class PhoneStorageOptionDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(PhoneStorageOption, id=pk)
        obj.is_active = False
        obj.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"success": True, "status": "deleted"})


class PhoneStorageOptionRestoreView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(PhoneStorageOption, id=pk)
        obj.is_active = True
        obj.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"success": True, "status": "restored"})


class PhoneStorageOptionPermanentDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(PhoneStorageOption, id=pk, is_active=False)
        obj.delete()
        return JsonResponse({"success": True, "status": "deleted-permanent"})


class PhoneRamOptionCreateView(SuperAdminRequiredMixin, View):
    def post(self, request):
        from apps.catalog.models import PhoneRamOption
        label = request.POST.get("label", "").strip()
        if not label:
            return JsonResponse({"error": "RAM capacity is required"}, status=400)
        obj, created = PhoneRamOption.objects.get_or_create(label=label)
        if not obj.is_active:
            obj.is_active = True
            obj.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"id": str(obj.id), "label": obj.label, "created": created})


class PhoneRamOptionDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        from apps.catalog.models import PhoneRamOption
        obj = get_object_or_404(PhoneRamOption, id=pk)
        obj.is_active = False
        obj.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"success": True, "status": "deleted"})


class PhoneRamOptionRestoreView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        from apps.catalog.models import PhoneRamOption
        obj = get_object_or_404(PhoneRamOption, id=pk)
        obj.is_active = True
        obj.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"success": True, "status": "restored"})


class PhoneRamOptionPermanentDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        from apps.catalog.models import PhoneRamOption
        obj = get_object_or_404(PhoneRamOption, id=pk, is_active=False)
        obj.delete()
        return JsonResponse({"success": True, "status": "deleted-permanent"})


class PhoneColorOptionCreateView(SuperAdminRequiredMixin, View):
    def post(self, request):
        name = request.POST.get("name", "").strip()
        color_hex = request.POST.get("color_hex", "").strip()
        if not name:
            return JsonResponse({"error": "Colour name is required"}, status=400)
        obj, created = PhoneColorOption.objects.get_or_create(name=name)
        obj.color_hex = color_hex
        obj.is_active = True
        obj.save(update_fields=["color_hex", "is_active", "updated_at"])
        return JsonResponse({"id": str(obj.id), "name": obj.name, "color_hex": obj.color_hex, "created": created})


class PhoneColorOptionDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(PhoneColorOption, id=pk)
        obj.is_active = False
        obj.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"success": True, "status": "deleted"})


class PhoneColorOptionRestoreView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(PhoneColorOption, id=pk)
        obj.is_active = True
        obj.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"success": True, "status": "restored"})


class PhoneColorOptionPermanentDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(PhoneColorOption, id=pk, is_active=False)
        obj.delete()
        return JsonResponse({"success": True, "status": "deleted-permanent"})


class PhoneModelVariantCreateView(SuperAdminRequiredMixin, View):
    def sync_option_presets(self, ram_value, storage_value, color_value, color_hex=""):
        ram_value = (ram_value or "").strip()
        storage_value = (storage_value or "").strip()
        color_value = (color_value or "").strip()
        if ram_value:
            from apps.catalog.models import PhoneRamOption
            PhoneRamOption.objects.get_or_create(label=ram_value)
        if storage_value:
            PhoneStorageOption.objects.get_or_create(label=storage_value)
        if color_value:
            option, _ = PhoneColorOption.objects.get_or_create(name=color_value)
            if color_hex and option.color_hex != color_hex:
                option.color_hex = color_hex
                option.save(update_fields=["color_hex", "updated_at"])

    def post(self, request):
        phone_model_id = request.POST.get("phone_model_id", "").strip()
        ram = request.POST.get("ram", "").strip()
        storage = request.POST.get("storage", "").strip()
        color = request.POST.get("color", "").strip()
        color_hex = request.POST.get("color_hex", "").strip()

        if not phone_model_id:
            return JsonResponse({"error": "phone_model_id is required"}, status=400)

        phone_model = get_object_or_404(PhoneModel, id=phone_model_id)
        rams = [item.strip() for item in ram.split(",") if item.strip()] or [""]
        storages = [item.strip() for item in storage.split(",") if item.strip()] or [""]
        colors = [item.strip() for item in color.split(",") if item.strip()] or [""]
        created = []
        for ram_value in rams:
            for storage_value in storages:
                for color_value in colors:
                    self.sync_option_presets(ram_value, storage_value, color_value, color_hex)
                    obj = PhoneModelVariant.objects.create(
                        phone_model=phone_model,
                        ram=ram_value,
                        storage=storage_value,
                        color=color_value,
                        color_hex=color_hex if len(colors) == 1 else "",
                    )
                    created.append({
                        "id": str(obj.id),
                        "display_name": obj.display_name,
                        "ram": obj.ram,
                        "storage": obj.storage,
                        "color": obj.color,
                        "color_hex": obj.color_hex,
                        "phone_model_id": str(phone_model.id),
                    })
        return JsonResponse({
            "success": True,
            "variants": created,
            "count": len(created),
        })


class PhoneModelVariantUpdateView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(PhoneModelVariant, id=pk)
        ram = request.POST.get("ram", obj.ram).strip()
        storage = request.POST.get("storage", obj.storage).strip()
        color = request.POST.get("color", obj.color).strip()
        obj.color_hex = request.POST.get("color_hex", obj.color_hex).strip()
        rams = [item.strip() for item in ram.split(",") if item.strip()] or [ram]
        storages = [item.strip() for item in storage.split(",") if item.strip()] or [storage]
        colors = [item.strip() for item in color.split(",") if item.strip()] or [color]
        if len(rams) > 1 or len(storages) > 1 or len(colors) > 1:
            created = []
            base_model = obj.phone_model
            obj.delete()
            for ram_value in rams:
                for storage_value in storages:
                    for color_value in colors:
                        PhoneModelVariantCreateView().sync_option_presets(ram_value, storage_value, color_value, obj.color_hex)
                        variant = PhoneModelVariant.objects.create(
                            phone_model=base_model,
                            ram=ram_value,
                            storage=storage_value,
                            color=color_value,
                            color_hex=obj.color_hex if len(colors) == 1 else "",
                        )
                        created.append({"id": str(variant.id), "display_name": variant.display_name})
            return JsonResponse({"success": True, "variants": created, "count": len(created)})
        obj.ram = ram
        obj.storage = storage
        obj.color = color
        PhoneModelVariantCreateView().sync_option_presets(ram, storage, color, obj.color_hex)
        obj.save(update_fields=["ram", "storage", "color", "color_hex", "updated_at"])
        return JsonResponse({"id": str(obj.id), "display_name": obj.display_name})


class PhoneModelVariantDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(PhoneModelVariant, id=pk)
        obj.is_active = False
        obj.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"success": True, "status": "deleted"})


class PhoneModelVariantRestoreView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(PhoneModelVariant, id=pk)
        obj.is_active = True
        obj.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"success": True, "status": "restored"})


class PhoneModelVariantPermanentDeleteView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(PhoneModelVariant, id=pk, is_active=False)
        obj.delete()
        return JsonResponse({"success": True, "status": "deleted-permanent"})


class PhoneModelVariantsAPIView(SuperAdminRequiredMixin, View):
    """GET /api/phone-models/<model_id>/variants/ — returns variants as JSON for cascading dropdowns."""
    def get(self, request, model_id):
        variants = PhoneModelVariant.objects.filter(phone_model_id=model_id, is_active=True).order_by("sort_order", "ram", "storage", "color")
        data = [{"id": str(v.id), "label": v.display_name} for v in variants]
        return JsonResponse({"variants": data})


class PhoneModelsAPIView(SuperAdminRequiredMixin, View):
    """GET /api/phone-models/?platform_id=<id>&brand_id=<id> — cascading dropdown support."""
    def get(self, request):
        normalize_comma_separated_phone_models()
        qs = PhoneModel.objects.select_related("brand", "platform").filter(is_active=True).order_by("sort_order", "name")
        platform_id = request.GET.get("platform_id")
        brand_id = request.GET.get("brand_id")
        if platform_id:
            qs = qs.filter(platform_id=platform_id)
        if brand_id:
            qs = qs.filter(brand_id=brand_id)
        data = [
            {
                "id": str(m.id),
                "name": m.name,
                "label": m.display_name,
                "display_name": m.display_name,
                "platform_id": str(m.platform_id),
                "brand_id": str(m.brand_id) if m.brand_id else "",
            }
            for m in qs
        ]
        return JsonResponse({"models": data})


class PhoneModelsAdminAPIView(SuperAdminRequiredMixin, View):
    """Filterable, paginated catalogue explorer for the large Device Models registry."""

    def get(self, request):
        qs = PhoneModel.objects.select_related("brand", "platform").prefetch_related("variants").filter(is_active=True)
        platform_id = request.GET.get("platform_id", "").strip()
        brand_id = request.GET.get("brand_id", "").strip()
        query = request.GET.get("q", "").strip()
        variant_query = request.GET.get("variant", "").strip()
        if platform_id:
            qs = qs.filter(platform_id=platform_id)
        if brand_id:
            qs = qs.filter(brand_id=brand_id)
        if query:
            qs = qs.filter(Q(name__icontains=query) | Q(brand__name__icontains=query) | Q(platform__name__icontains=query))
        if variant_query:
            qs = qs.filter(variants__is_active=True).filter(
                Q(variants__ram__icontains=variant_query)
                | Q(variants__storage__icontains=variant_query)
                | Q(variants__color__icontains=variant_query)
            )
        qs = qs.distinct().order_by("platform__name", "brand__name", "sort_order", "name")
        try:
            page_number = max(1, int(request.GET.get("page", 1)))
        except (TypeError, ValueError):
            page_number = 1
        try:
            page_size = min(50, max(10, int(request.GET.get("page_size", 20))))
        except (TypeError, ValueError):
            page_size = 20
        page = Paginator(qs, page_size).get_page(page_number)
        results = []
        for model in page.object_list:
            variants = [
                {"id": str(v.id), "label": v.display_name, "ram": v.ram, "storage": v.storage, "color": v.color}
                for v in model.variants.filter(is_active=True).order_by("sort_order", "storage", "color")
            ]
            results.append({
                "id": str(model.id), "name": model.name, "display_name": model.display_name,
                "brand": model.brand.name if model.brand else "—", "platform": model.platform.get_name_display(),
                "platform_id": str(model.platform_id), "released_year": model.released_year,
                "variant_count": len(variants), "variants": variants,
            })
        return JsonResponse({
            "results": results,
            "page": page.number,
            "pages": page.paginator.num_pages,
            "total": page.paginator.count,
            "page_size": page_size,
        })


class PhoneBrandsAPIView(SuperAdminRequiredMixin, View):
    """GET /api/phone-brands/?platform_id=<id> — returns brands for given platform."""
    def get(self, request):
        qs = PhoneBrand.objects.filter(is_active=True).order_by("sort_order", "name")
        platform_id = request.GET.get("platform_id")
        if platform_id:
            qs = qs.filter(platform_id=platform_id)
        data = [{"id": str(b.id), "label": b.name} for b in qs]
        return JsonResponse({"brands": data})
