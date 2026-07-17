import csv
import json
from datetime import datetime, timedelta

from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Case, F, IntegerField, Q, Value, When
from django.db.models.functions import Coalesce
from django.forms import modelform_factory
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
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
    BackofficeUserCreateForm,
    BackofficeUserUpdateForm,
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
from apps.orders.models import Order
from apps.orders.forms import OrderStatusForm, OrderWorkflowSettingForm, EmailTemplateForm
from apps.orders.services import update_order_status, generate_delivery_label, get_order_workflow_setting
from apps.orders.models import OrderWorkflowSetting
from apps.payments.models import Invoice
from apps.payments.services import generate_invoice_for_order
from apps.settings_app.models import Setting
from apps.notifications.models import NotificationTemplate
from apps.notifications.services import ensure_order_email_templates


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
        user = self.request.user
        if user.is_authenticated:
            return user
        return None

    def dispatch(self, request, *args, **kwargs):
        self.portal_user = self.get_portal_user()
        if self.portal_user:
            request.user = self.portal_user
        return super().dispatch(request, *args, **kwargs)

    def test_func(self):
        user = getattr(self, "portal_user", None) or self.request.user
        return bool(user) and user.is_authenticated and (
            user.is_superuser
            or user.global_roles.filter(role__code=ROLE_SUPER_ADMIN, account_membership__isnull=True).exists()
        )

    def handle_no_permission(self):
        user = self.request.user
        if user.is_authenticated:
            has_retailer_membership = user.account_memberships.filter(
                status="active",
                account__retailer_profile__isnull=False,
            ).exists()
            if has_retailer_membership:
                return redirect("retailers:dashboard")
        return super().handle_no_permission()

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
        if request.user.is_authenticated:
            is_super_admin = request.user.is_superuser or request.user.global_roles.filter(
                role__code=ROLE_SUPER_ADMIN,
                account_membership__isnull=True,
            ).exists()
            if is_super_admin:
                request.session[self.session_user_key] = str(request.user.pk)
                return redirect("backoffice:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        self.request.session[self.session_user_key] = str(form.get_user().pk)
        self.request.session.modified = True
        return redirect(self.get_success_url())

    def get_success_url(self):
        user_id = self.request.session.get(self.session_user_key)
        user = User.objects.filter(pk=user_id, is_active=True).first() if user_id else self.request.user
        is_super_admin = user.is_superuser or user.global_roles.filter(
            role__code=ROLE_SUPER_ADMIN,
            account_membership__isnull=True,
        ).exists()
        if not is_super_admin:
            has_retailer_membership = user.account_memberships.filter(
                status="active",
                account__retailer_profile__isnull=False,
            ).exists()
            if has_retailer_membership:
                return reverse("retailers:dashboard")
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
                "sidebar_groups": self.get_sidebar_groups(),
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
        c.update({"page_title": "Orders", "orders": Order.objects.select_related("customer", "retailer").order_by("-created_at"), "sidebar_groups": grouped_modules(), "module_key_active": None, "active_group": "Commerce"})
        return c


class BackofficeOrderStatusView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk); form = OrderStatusForm(request.POST)
        if form.is_valid(): update_order_status(order, form.cleaned_data["status"], actor=getattr(self, "portal_user", request.user))
        return redirect("backoffice:orders")


class BackofficeOrderInvoiceView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk); generate_invoice_for_order(order, actor=getattr(self, "portal_user", request.user)); return redirect("backoffice:order-invoice-print", pk=pk)


class BackofficeOrderLabelView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk); generate_delivery_label(order, actor=getattr(self, "portal_user", request.user)); return redirect("backoffice:order-label-print", pk=pk)


class BackofficeOrderInvoicePrintView(SuperAdminRequiredMixin, TemplateView):
    template_name = "orders/invoice_print.html"
    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs); order = get_object_or_404(Order, pk=kwargs["pk"]); c.update({"order": order, "invoice": Invoice.objects.filter(order=order).prefetch_related("items").first(), "invoice_design": Setting.objects.filter(key="invoice_design").values_list("value", flat=True).first() or {}}); return c


class BackofficeOrderLabelPrintView(SuperAdminRequiredMixin, TemplateView):
    template_name = "orders/label_print.html"
    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs); order = get_object_or_404(Order, pk=kwargs["pk"]); c.update({"order": order, "label": generate_delivery_label(order, actor=getattr(self, "portal_user", self.request.user))}); return c


class BackofficeInvoiceDesignView(SuperAdminRequiredMixin, FormView):
    template_name = "backoffice/invoice_design.html"
    def get_initial(self):
        return Setting.objects.filter(key="invoice_design").values_list("value", flat=True).first() or {"company_name": "CommerceOS", "footer_text": "Thank you for your business.", "accent_color": "#e04420"}
    def get_form_class(self):
        from django import forms
        return type("InvoiceDesignForm", (forms.Form,), {"company_name": forms.CharField(required=False), "footer_text": forms.CharField(required=False, widget=forms.Textarea), "accent_color": forms.CharField(required=False)})
    def form_valid(self, form):
        Setting.objects.update_or_create(key="invoice_design", defaults={"value": form.cleaned_data}); messages.success(self.request, "Invoice design saved."); return redirect("backoffice:invoice-design")
    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs); c.update({"page_title": "Invoice Design (Admin only)", "sidebar_groups": grouped_modules(), "module_key_active": None, "active_group": "Platform"}); return c

    def get_sidebar_groups(self):
        return grouped_modules()


class BackofficeOrderWorkflowSettingsView(SuperAdminRequiredMixin, TemplateView):
    template_name = "backoffice/order_workflow_settings.html"
    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs)
        c.update({"page_title": "Order Workflow Settings", "workflow_rows": [(r, OrderWorkflowSettingForm(instance=get_order_workflow_setting(r))) for r in Retailer.objects.filter(is_active=True).order_by("display_name")], "sidebar_groups": grouped_modules(), "module_key_active": None, "active_group": "Commerce"})
        return c
    def post(self, request, *args, **kwargs):
        retailer = get_object_or_404(Retailer, pk=request.POST.get("retailer_id"))
        form = OrderWorkflowSettingForm(request.POST, instance=get_order_workflow_setting(retailer))
        if form.is_valid():
            form.save(); messages.success(request, f"Workflow settings saved for {retailer.display_name}.")
        return redirect("backoffice:order-workflow-settings")


class BackofficeEmailTemplateListView(SuperAdminRequiredMixin, TemplateView):
    template_name = "backoffice/email_templates.html"
    def get_context_data(self, **kwargs):
        ensure_order_email_templates()
        c = super().get_context_data(**kwargs)
        c.update({"page_title": "Email Templates", "templates": NotificationTemplate.objects.filter(channel=NotificationTemplate.CHANNEL_EMAIL).order_by("event_name"), "sidebar_groups": grouped_modules(), "module_key_active": None, "active_group": "Platform"})
        return c


class BackofficeEmailTemplateUpdateView(SuperAdminRequiredMixin, UpdateView):
    template_name = "backoffice/email_template_form.html"
    model = NotificationTemplate
    form_class = EmailTemplateForm
    def get_queryset(self): return NotificationTemplate.objects.filter(channel=NotificationTemplate.CHANNEL_EMAIL)
    def get_success_url(self): return reverse("backoffice:email-templates")
    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs); c.update({"page_title": "Edit Email Template", "sidebar_groups": grouped_modules(), "module_key_active": None, "active_group": "Platform"}); return c


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
            return redirect(self.get_success_url())

        response = super().form_valid(form)
        if module == "attributes":
            self.save_color_values(self.object, form.cleaned_data.get("color_values_payload"))
        return response

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
        return response

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
