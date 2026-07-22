import csv
import json
from datetime import datetime, timedelta
from urllib.parse import urlencode

from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Case, F, IntegerField, Q, Value, When
from django.db.models.functions import Coalesce
from django.forms import modelform_factory
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
)
from apps.backoffice.registry import MODULES, grouped_modules
from apps.catalog.models import (
    AttributeValue, ProductAttribute, Product, ProductVariantAttributeValue,
    PhonePlatform, PhoneBrand, PhoneModel, PhoneModelVariant,
    PhoneStorageOption, PhoneColorOption, PhoneRamOption,
)
from apps.catalog.services import normalize_comma_separated_phone_models, split_comma_values, sync_split_phone_models_from_combined
from apps.rbac.constants import ROLE_SUPER_ADMIN
from apps.users.models import User
from apps.notifications.models import Notification
from apps.inventory.models import LowStockAlert, StockItem
from apps.inventory.services import canonical_stock_items
from apps.retailers.models import Retailer
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

    def handle_no_permission(self):
        # The URL selects the portal. Never send an unauthenticated or
        # retailer-session request from /admin/ to the retailer portal.
        return redirect(self.login_url)

    def get_context_data(self, **kwargs):
        """Expose real, relevant notifications in every backoffice view."""
        context = super().get_context_data(**kwargs)
        user = getattr(self, "portal_user", None) or self.request.user
        notification_queryset = Notification.objects.filter(Q(user__isnull=True) | Q(user=user))
        notifications = notification_queryset.order_by("-created_at")[:8]
        context.update(
            {
                "backoffice_notifications": notifications,
                "backoffice_unread_notification_count": notification_queryset.filter(read_at__isnull=True).count(),
            }
        )
        return context


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
        return {"links": [{"text": text, "target": target, "manual": ""} for text, target in zip(labels, targets)], "trust": [{"title": "Secure checkout", "subtitle": "Protected payments"}, {"title": "Fast delivery", "subtitle": "Reliable order updates"}, {"title": "Easy returns", "subtitle": "Simple return process"}, {"title": "Customer support", "subtitle": "Here when you need us"}], "brand_mode": "text", "brand_image": "", "trust_color": "#ffffff", "trust_muted_color": "#8f99aa", "trust_font": "Inter", "copyright": "© 2026 Nuboxed. All rights reserved.", "copyright_align": "left", "payment_images": [], "payment_width": 54, "payment_height": 32, "payment_fit": "contain"}

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
        values = {"links": links, "trust": trust, "brand_mode": request.POST.get("brand_mode", "text"), "brand_image": request.POST.get("brand_image", "").strip(), "trust_color": request.POST.get("trust_color", "#ffffff"), "trust_muted_color": request.POST.get("trust_muted_color", "#8f99aa"), "trust_font": request.POST.get("trust_font", "Inter"), "copyright": request.POST.get("copyright", "").strip(), "copyright_align": request.POST.get("copyright_align", "left"), "payment_images": [x.strip() for x in request.POST.get("payment_images", "").splitlines() if x.strip()], "payment_width": max(24, min(int(request.POST.get("payment_width") or 54), 180)), "payment_height": max(20, min(int(request.POST.get("payment_height") or 32), 100)), "payment_fit": request.POST.get("payment_fit", "contain")}
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


class BackofficeContactSettingsView(SuperAdminRequiredMixin, View):
    template_name = "backoffice/contact_settings.html"

    def defaults(self):
        return {
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
        return redirect("backoffice:contact-settings")


class BackofficeProductPageSettingsView(SuperAdminRequiredMixin, View):
    template_name = "backoffice/product_page_settings.html"

    def defaults(self):
        return {
            "visit_store_prefix": "Visit the", "reviews_label": "Reviews", "highlight_1": "Verified product data from Nuboxed", "highlight_2": "Store-aware delivery estimate and seller comparison", "highlight_3": "Shop confidently from verified retailers.", "sale_countdown": "Hurry up! Sale ends in:", "delivery_label": "Est. Delivery Time", "add_to_cart": "ADD TO CART", "buy_now": "BUY NOW", "add_wishlist": "Add to Wishlist", "add_compare": "Add to Compare", "share_label": "Share", "policy_1": "Free Shipping & Returns: Available on all orders over $99.", "policy_2": "Estimated Delivery: Orders are typically dispatched within 24 hours.", "policy_3": "Security Policy: Ensuring top-level security for your data and transactions.", "description_tab": "Description", "details_tab": "Product Details", "description_heading": "Its much more than mobile product", "description_fallback": "Shop the most popular featured products.", "description_note": "Your trusted marketplace page, wired to admin product data and structured for fast comparison, clear pricing, and clean buying actions.", "specifications_heading": "PRODUCT DETAILS", "related_heading": "You might also like", "category_heading_suffix": "in the same category:", "comments_heading": "Comments", "grade_label": "Grade", "write_review": "WRITE YOUR REVIEW", "view_all_comments": "View all comments", "customer_voice": "Customer voice", "all_comments": "All comments", "review_modal_heading": "Write your review", "review_title_label": "Title", "review_name_label": "Your name", "review_text_label": "Review", "review_terms": "I agree to the terms and the privacy policy", "required_note": "* Required fields", "cancel_button": "CANCEL", "send_button": "SEND", "review_success": "Thank you. Your review has been submitted successfully.", "quick_brand_fallback": "Store", "quick_delivery": "Est. Delivery Time 2-3 Days", "quick_reviews": "Reviews", "quick_point_1": "Verified product data from Nuboxed", "quick_point_2": "Store-aware delivery estimate and seller comparison", "quick_ram_label": "RAM:", "quick_storage_label": "Internal Storage:", "quick_color_label": "Color:", "quick_add_to_cart": "ADD TO CART", "quick_buy_now": "BUY NOW", "quick_wishlist": "Add to Wishlist", "quick_compare": "Add to Compare", "quick_stock": "Available Stock", "quick_share": "Share", "quick_save_prefix": "Save",
        }

    def get(self, request, *args, **kwargs):
        values = self.defaults()
        values.update(Setting.objects.filter(key="product_page_customization", is_active=True).values_list("value", flat=True).first() or {})
        values.setdefault("show_share_icons", "1")
        values.setdefault("share_platforms", ["facebook", "x", "linkedin", "pinterest", "email"])
        return render(request, self.template_name, {"settings": values, "sidebar_groups": grouped_modules(), "active_group": "Page Settings", "page_title": "Product Page Settings"})

    def post(self, request, *args, **kwargs):
        values = {key: request.POST.get(key, "").strip() for key in self.defaults()}
        values["show_share_icons"] = "1" if request.POST.get("show_share_icons") == "1" else "0"
        values["share_platforms"] = [item for item in request.POST.getlist("share_platforms") if item in {"facebook", "x", "linkedin", "pinterest", "email"}]
        Setting.objects.update_or_create(key="product_page_customization", defaults={"value": values, "is_active": True})
        messages.success(request, "Product page settings saved successfully.")
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
        return JsonResponse({"id": str(obj.id), "name": obj.name, "platform_id": str(platform.id)})


class PhoneBrandUpdateView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        brand = get_object_or_404(PhoneBrand, id=pk)
        name = request.POST.get("name", "").strip()
        if name:
            brand.name = name
            brand.save(update_fields=["name", "updated_at"])
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


class PhoneBrandsAPIView(SuperAdminRequiredMixin, View):
    """GET /api/phone-brands/?platform_id=<id> — returns brands for given platform."""
    def get(self, request):
        qs = PhoneBrand.objects.filter(is_active=True).order_by("sort_order", "name")
        platform_id = request.GET.get("platform_id")
        if platform_id:
            qs = qs.filter(platform_id=platform_id)
        data = [{"id": str(b.id), "label": b.name} for b in qs]
        return JsonResponse({"brands": data})
