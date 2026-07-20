from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.http import Http404, JsonResponse
from django.db.models import Count, Q
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.generic import CreateView, FormView, TemplateView, UpdateView, View
from django.utils import timezone
import json
import uuid

from apps.backoffice.views import SuperAdminRequiredMixin
from apps.retailers.forms import RetailerLoginForm, RetailerPasswordChangeForm, RetailerProfileForm, StoreForm, StoreStaffInviteForm
from apps.retailers.models import Retailer
from apps.retailers.services import add_store_staff, approve_retailer, unique_slug
from apps.catalog.models import Product, ProductAttribute, ProductVariant
from apps.stores.models import Store, StoreRating
from apps.users.models import User
from apps.users.services import generate_unique_username
from apps.settings_app.forms import RetailerSaleCountdownSettingForm
from apps.settings_app.models import SaleCountdownSetting
from apps.orders.models import Coupon, Order
from apps.orders.forms import OrderStatusForm, OrderWorkflowSettingForm
from apps.orders.services import build_order_timeline, coupon_feature_enabled, get_order_workflow_setting, get_order_workflow_setting_for_order, update_order_status, generate_delivery_label
from apps.payments.models import Invoice, PaymentTransaction
from apps.payments.services import generate_invoice_for_order, process_refund, amount_in_words
from apps.common.security import build_public_url
from decimal import Decimal, InvalidOperation
from django.template.response import TemplateResponse


@method_decorator([never_cache, ensure_csrf_cookie], name="dispatch")
class RetailerLoginView(LoginView):
    template_name = "retailer/login.html"
    authentication_form = RetailerLoginForm
    redirect_authenticated_user = False
    session_user_key = "retailer_user_id"

    def dispatch(self, request, *args, **kwargs):
        portal_user = None
        portal_user_id = request.session.get(self.session_user_key)
        if portal_user_id:
            portal_user = User.objects.filter(pk=portal_user_id, is_active=True).first()
        if portal_user and portal_user.account_memberships.filter(
            status="active",
            account__retailer_profile__isnull=False,
        ).exists():
            return redirect("retailers:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        self.request.session[self.session_user_key] = str(form.get_user().pk)
        self.request.session.modified = True
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("retailers:dashboard")


class RetailerLogoutView(LogoutView):
    next_page = reverse_lazy("retailers:login")

    @staticmethod
    def clear_portal_session(request):
        # Keep the admin portal session intact, but always persist removal of
        # the retailer portal identity immediately. This matters when the
        # login page is open in another tab using the same browser session.
        request.session.pop(RetailerLoginView.session_user_key, None)
        request.session.modified = True
        request.session.save()

    def get(self, request, *args, **kwargs):
        self.clear_portal_session(request)
        return redirect(self.next_page)

    def post(self, request, *args, **kwargs):
        self.clear_portal_session(request)
        return redirect(self.next_page)


class RetailerPortalMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = reverse_lazy("retailers:login")
    session_user_key = RetailerLoginView.session_user_key

    def get_portal_user(self):
        user_id = self.request.session.get(self.session_user_key)
        if user_id:
            user = User.objects.filter(pk=user_id, is_active=True).first()
            if user:
                return user
            self.request.session.pop(self.session_user_key, None)
            self.request.session.modified = True
        return None

    def dispatch(self, request, *args, **kwargs):
        self.portal_user = self.get_portal_user()
        if self.portal_user:
            request.user = self.portal_user
        return super().dispatch(request, *args, **kwargs)

    def get_membership(self):
        user = getattr(self, "portal_user", None)
        if not user:
            raise Http404("Retailer login required.")
        if user.is_superuser or user.global_roles.filter(
            role__code="super_admin",
            account_membership__isnull=True,
        ).exists():
            raise Http404("Retailer membership not found.")
        membership = (
            user.account_memberships.select_related("account__retailer_profile", "store")
            .filter(status="active", account__retailer_profile__isnull=False)
            .first()
        )

        if not membership:
            raise Http404("Retailer membership not found.")
        return membership

    def get_retailer(self):
        return self.get_membership().account.retailer_profile

    def has_retailer_permission(self, permission_code):
        retailer = self.get_retailer()
        user = getattr(self, "portal_user", None)
        if not user:
            return False
        return user.has_api_permission(permission_code, account=retailer.account)

    def test_func(self):
        try:
            self.get_membership()
            return True
        except Http404:
            return False

    def handle_no_permission(self):
        return redirect("retailers:login")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        retailer = self.get_retailer()
        stores = self.get_store_queryset(retailer)
        context.update(
            {
                "retailer": retailer,
                "stores": stores,
                "primary_store": self.get_primary_store(retailer),
                "can_manage_sale_countdown": self.has_retailer_permission("sale_countdown.manage"),
                "can_manage_coupons": coupon_feature_enabled(),
            }
        )
        return context

    def get_store_queryset(self, retailer=None):
        retailer = retailer or self.get_retailer()
        queryset = retailer.stores.all()

        memberships = self.request.user.account_memberships.filter(
            account=retailer.account,
            status="active",
            is_active=True,
        )
        if self.request.user == retailer.account.owner or memberships.filter(store__isnull=True).exists():
            return queryset

        store_ids = memberships.exclude(store__isnull=True).values_list("store_id", flat=True)
        return queryset.filter(id__in=store_ids)

    def get_primary_store(self, retailer=None):
        return (
            self.get_store_queryset(retailer or self.get_retailer())
            .order_by("-is_active", "-updated_at", "-created_at")
            .first()
        )

    def get_staff_memberships_queryset(self, retailer=None, include_inactive=False):
        retailer = retailer or self.get_retailer()
        stores = self.get_store_queryset(retailer)
        queryset = (
            retailer.account.memberships.select_related("user", "store")
            .prefetch_related("user_roles__role")
            .filter(Q(store__in=stores) | Q(store__isnull=True))
            .exclude(user=retailer.account.owner)
            .exclude(user__is_staff=True)
            .exclude(user__is_superuser=True)
            .exclude(user__global_roles__role__code="super_admin", user__global_roles__account_membership__isnull=True)
            .distinct()
        )
        if not include_inactive:
            queryset = queryset.filter(is_active=True, status="active")
        return queryset


class RetailerSaleCountdownListView(RetailerPortalMixin, TemplateView):
    template_name = "retailer/sale_countdown_settings.html"

    def test_func(self):
        return super().test_func() and self.has_retailer_permission("sale_countdown.manage")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        retailer = self.get_retailer()
        context.update({
            "page_title": "Sale Countdown",
            "sale_settings": SaleCountdownSetting.objects.filter(retailer=retailer).select_related("category").order_by("category__name", "-updated_at"),
            "form": RetailerSaleCountdownSettingForm(retailer=retailer),
        })
        return context

    def post(self, request, *args, **kwargs):
        retailer = self.get_retailer()
        form = RetailerSaleCountdownSettingForm(request.POST, retailer=retailer)
        if form.is_valid():
            form.save()
            messages.success(request, "Sale countdown setting saved.")
            return redirect("retailers:sale-countdown")
        context = self.get_context_data(**kwargs)
        context["form"] = form
        return self.render_to_response(context)


class RetailerSaleCountdownUpdateView(RetailerPortalMixin, UpdateView):
    template_name = "retailer/sale_countdown_edit.html"
    form_class = RetailerSaleCountdownSettingForm

    def test_func(self):
        return super().test_func() and self.has_retailer_permission("sale_countdown.manage")

    def get_queryset(self):
        return SaleCountdownSetting.objects.filter(retailer=self.get_retailer())

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["retailer"] = self.get_retailer()
        return kwargs

    def get_success_url(self):
        return reverse("retailers:sale-countdown")


class RetailerSaleCountdownDeleteView(RetailerPortalMixin, View):
    def test_func(self):
        return super().test_func() and self.has_retailer_permission("sale_countdown.manage")

    def post(self, request, pk):
        SaleCountdownSetting.objects.filter(pk=pk, retailer=self.get_retailer()).update(is_active=False)
        messages.success(request, "Sale countdown setting disabled.")
        return redirect("retailers:sale-countdown")


class RetailerOrdersView(RetailerPortalMixin, TemplateView):
    template_name = "retailer/orders.html"
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"page_title": "Orders", "orders": Order.objects.filter(retailer=self.get_retailer()).select_related("customer").prefetch_related("items__product", "items__variant", "timeline_entries__actor").order_by("-created_at")})
        return context


class RetailerOrderDetailView(RetailerPortalMixin, TemplateView):
    template_name = "orders/retailer_detail.html"

    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs)
        order = get_object_or_404(Order.objects.select_related("customer", "retailer", "address").prefetch_related(
            "items__product__media_items", "items__product__phone_variant__phone_model", "items__warehouse",
            "items__variant__attribute_values__attribute", "items__variant__attribute_values__option",
            "timeline_entries", "payment_transactions__gateway", "payment_transactions__refunds", "invoices__items", "shipments__courier_partner",
            "return_requests__timeline_entries", "return_requests__items__order_item__product",
        ), pk=kwargs["pk"], retailer=self.get_retailer())
        order_items = list(order.items.all())
        cancellation_entry = order.timeline_entries.filter(status=Order.STATUS_CANCELLED).order_by("-occurred_at").first()
        refund_transactions = [refund for transaction in order.payment_transactions.all() for refund in transaction.refunds.all()]
        c.update({"page_title": f"Order {order.number}", "order": order, "portal": "retailer", "order_detail_page": True, "order_item_count": len(order_items), "order_unit_count": sum(item.quantity for item in order_items), "order_can_cancel": order.status not in {Order.STATUS_CANCELLED, Order.STATUS_DELIVERED, Order.STATUS_RETURNED, Order.STATUS_REFUNDED}, "cancellation_entry": cancellation_entry, "refund_transactions": refund_transactions})
        return c


class RetailerOrderStatusView(RetailerPortalMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, retailer=self.get_retailer())
        form = OrderStatusForm(request.POST)
        if form.is_valid():
            updated_order = update_order_status(order, form.cleaned_data["status"], actor=getattr(self, "portal_user", request.user))
            if getattr(updated_order, "_fulfillment_warning", ""):
                messages.warning(request, f"Order status updated, but courier booking is pending: {updated_order._fulfillment_warning}")
        return redirect("retailers:orders")


class RetailerOrderCancelView(RetailerPortalMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, retailer=self.get_retailer())
        if order.status in {Order.STATUS_CANCELLED, Order.STATUS_DELIVERED, Order.STATUS_RETURNED, Order.STATUS_REFUNDED}:
            messages.error(request, "This order cannot be cancelled in its current status.")
        else:
            update_order_status(order, Order.STATUS_CANCELLED, actor=getattr(self, "portal_user", request.user), note=request.POST.get("cancellation_reason", "Customer requested"))
            messages.success(request, f"Order {order.number} was cancelled successfully.")
        return redirect("retailers:order-detail", pk=order.pk)


class RetailerOrderTransactionView(RetailerPortalMixin, View):
    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk, retailer=self.get_retailer())
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


class RetailerOrderRefundView(RetailerPortalMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, retailer=self.get_retailer())
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
        return redirect("retailers:order-detail", pk=order.pk)


class RetailerOrderInvoiceView(RetailerPortalMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, retailer=self.get_retailer())
        setting = get_order_workflow_setting_for_order(order)
        if setting.allow_manual_invoice: generate_invoice_for_order(order, actor=getattr(self, "portal_user", request.user))
        return redirect("retailers:order-invoice-print", pk=order.pk)


class RetailerOrderLabelView(RetailerPortalMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, retailer=self.get_retailer())
        if get_order_workflow_setting_for_order(order).allow_manual_label: generate_delivery_label(order, actor=getattr(self, "portal_user", request.user))
        return redirect("retailers:order-label-print", pk=order.pk)


@method_decorator(xframe_options_sameorigin, name="dispatch")
class RetailerOrderInvoicePrintView(RetailerPortalMixin, TemplateView):
    template_name = "orders/invoice_print.html"
    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs); order = get_object_or_404(Order, pk=kwargs["pk"], retailer=self.get_retailer()); invoice = generate_invoice_for_order(order, actor=getattr(self, "portal_user", self.request.user)); shipment = order.shipments.order_by("-created_at").first(); invoice_access_url = build_public_url(self.request, reverse("storefront:invoice-access", kwargs={"invoice_number": invoice.invoice_number})); c.update({"order": order, "invoice": invoice, "invoice_design": {}, "tracking_number": getattr(shipment, "tracking_number", ""), "amount_in_words": amount_in_words(invoice.total_amount or order.total_amount, invoice.currency or order.currency_code), "invoice_url_json": json.dumps(invoice_access_url), "invoice_access_url": invoice_access_url}); return c


@method_decorator(xframe_options_sameorigin, name="dispatch")
class RetailerOrderLabelPrintView(RetailerPortalMixin, TemplateView):
    template_name = "orders/label_print.html"
    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs); order = get_object_or_404(Order, pk=kwargs["pk"], retailer=self.get_retailer()); label = generate_delivery_label(order); payload = dict(label.payload); verification_url = build_public_url(self.request, reverse("storefront:label-verify", kwargs={"label_number": label.label_number})); payload["tracking_url"] = verification_url; payload["barcode_value"] = verification_url; c.update({"order": order, "label": label, "verification_url": verification_url, "label_payload_json": json.dumps(payload)}); return c


class RetailerOrderWorkflowSettingsView(RetailerPortalMixin, FormView):
    template_name = "retailer/order_settings.html"
    form_class = OrderWorkflowSettingForm
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs(); kwargs["instance"] = get_order_workflow_setting(self.get_retailer()); return kwargs
    def form_valid(self, form): form.save(); messages.success(self.request, "Order workflow settings saved."); return redirect("retailers:order-settings")
    def get_context_data(self, **kwargs): c = super().get_context_data(**kwargs); c["page_title"] = "Order Workflow Settings"; return c


class RetailerCouponsView(RetailerPortalMixin, TemplateView):
    template_name = "retailer/coupons.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        retailer = self.get_retailer()
        context.update({"page_title": "Coupons", "coupons": Coupon.objects.filter(retailer=retailer), "coupon_feature_enabled": coupon_feature_enabled()})
        return context

    def post(self, request):
        if not coupon_feature_enabled():
            messages.error(request, "Coupon management is disabled by the administrator.")
            return redirect("retailers:coupons")
        code = request.POST.get("code", "").strip().upper()
        try:
            value = request.POST.get("discount_value", "0")
            Coupon.objects.create(
                code=code,
                retailer=self.get_retailer(),
                discount_type=request.POST.get("discount_type", Coupon.TYPE_PERCENTAGE),
                discount_value=value,
                minimum_order_amount=request.POST.get("minimum_order_amount", "0") or 0,
                maximum_discount_amount=request.POST.get("maximum_discount_amount") or None,
                usage_limit=request.POST.get("usage_limit") or None,
                is_active=True,
            )
            messages.success(request, "Coupon created successfully.")
        except Exception as exc:
            messages.error(request, f"Coupon could not be created: {exc}")
        return redirect("retailers:coupons")



class RetailerDashboardView(RetailerPortalMixin, TemplateView):
    template_name = "retailer/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        retailer = self.get_retailer()
        memberships = self.get_staff_memberships_queryset(retailer)
        stores = self.get_store_queryset(retailer).order_by("-is_active", "-updated_at", "-created_at")
        product_count = Product.objects.filter(
            retailer=retailer,
            deleted_at__isnull=True,
        ).count()
        country_mix = list(
            stores.exclude(country_code="")
            .values("country_code")
            .annotate(total=Count("id"))
            .order_by("-total")[:5]
        )
        context.update(
            {
                "page_title": "Retailer Dashboard",
                "staff_count": memberships.count(),
                "approved": retailer.status == Retailer.STATUS_APPROVED,
                "connector_notice": "External marketplace connectors are managed only by Super Admin.",
                "stores": stores,
                "primary_store": self.get_primary_store(retailer),
                "product_count": product_count,
                "sales_chart_labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                "sales_chart_series": [18, 24, 21, 29, 36, 31, 44],
                "revenue_chart_series": [45, 58, 52, 66, 61, 74, 83],
                "country_mix": country_mix,
            }
        )
        return context


class RetailerProfileUpdateView(RetailerPortalMixin, UpdateView):
    template_name = "retailer/profile.html"
    form_class = RetailerProfileForm

    def get_object(self):
        return self.get_retailer()

    def get_success_url(self):
        messages.success(self.request, "Retailer profile updated.")
        return reverse("retailers:profile")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Retailer Profile"
        return context


class RetailerPasswordChangeView(RetailerPortalMixin, FormView):
    template_name = "retailer/change_password.html"
    form_class = RetailerPasswordChangeForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = getattr(self, "portal_user", None) or self.request.user
        return kwargs

    def get_success_url(self):
        messages.success(self.request, "Your retailer login password has been changed.")
        return reverse("retailers:change-password")

    def form_valid(self, form):
        user = getattr(self, "portal_user", None) or self.request.user
        user.set_password(form.cleaned_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        return super().form_valid(form)


class RetailerStoreCreateView(RetailerPortalMixin, CreateView):
    template_name = "retailer/store_form.html"
    form_class = StoreForm

    def get_existing_store(self):
        return self.get_primary_store(self.get_retailer())

    def get(self, request, *args, **kwargs):
        existing_store = self.get_existing_store()
        if existing_store:
            messages.info(request, "Store already exists. Manage the existing store here.")
            return redirect(reverse("retailers:store-edit", kwargs={"pk": existing_store.pk}))
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        existing_store = self.get_existing_store()
        if existing_store:
            messages.info(self.request, "This retailer already has one store. You can edit the existing store instead.")
            return redirect(reverse("retailers:store-edit", kwargs={"pk": existing_store.pk}))

        store = form.save(commit=False)
        store.retailer = self.get_retailer()
        store.slug = unique_slug(Store, store.name)
        store.save()
        self.object = store
        messages.success(self.request, "Store created successfully.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        if self.request.POST.get("save_action", "stay") == "stay" and getattr(self, "object", None):
            return reverse("retailers:store-edit", kwargs={"pk": self.object.pk})
        return reverse("retailers:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Create Store"
        return context


class RetailerStoreUpdateView(RetailerPortalMixin, UpdateView):
    template_name = "retailer/store_form.html"
    form_class = StoreForm

    def get_queryset(self):
        retailer = self.get_retailer()
        return self.get_store_queryset(retailer)

    def form_valid(self, form):
        form.instance.status = form.cleaned_data.get("status", Store.STATUS_DRAFT)
        form.instance.is_active = form.instance.status == Store.STATUS_ACTIVE
        return super().form_valid(form)

    def get_success_url(self):
        messages.success(self.request, "Store details updated.")
        if self.request.POST.get("save_action", "stay") == "stay":
            return reverse("retailers:store-edit", kwargs={"pk": self.object.pk})
        return reverse("retailers:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Store"
        return context


class RetailerStaffView(RetailerPortalMixin, TemplateView):
    template_name = "retailer/staff.html"

    def get_form(self):
        retailer = self.get_retailer()
        return StoreStaffInviteForm(
            self.request.POST or None,
            store_queryset=self.get_store_queryset(retailer),
        )

    def post(self, request, *args, **kwargs):
        action = request.POST.get("staff_action")
        if action in {"delete", "restore", "permanent_delete"}:
            retailer = self.get_retailer()
            selected_ids = request.POST.getlist("selected_memberships")
            memberships = self.get_staff_memberships_queryset(retailer, include_inactive=True).filter(id__in=selected_ids)
            if not selected_ids or not memberships.exists():
                messages.error(request, "Select at least one staff member.")
                return redirect(f"{reverse('retailers:staff')}?show=deleted" if action != "delete" else reverse("retailers:staff"))
            if action == "delete":
                memberships.update(is_active=False, status="inactive")
                messages.success(request, "Selected staff members moved to deleted staff.")
                return redirect("retailers:staff")
            if action == "restore":
                memberships.update(is_active=True, status="active")
                messages.success(request, "Selected staff members restored.")
                return redirect(f"{reverse('retailers:staff')}?show=deleted")
            memberships.delete()
            messages.success(request, "Selected staff members permanently deleted.")
            return redirect(f"{reverse('retailers:staff')}?show=deleted")

        form = self.get_form()
        retailer = self.get_retailer()
        if form.is_valid():
            user, _ = User.objects.get_or_create(
                email=form.cleaned_data["email"],
                defaults={
                    "username": generate_unique_username(form.cleaned_data["email"]),
                    "first_name": form.cleaned_data.get("first_name", ""),
                    "last_name": form.cleaned_data.get("last_name", ""),
                    "phone": form.cleaned_data.get("phone", ""),
                },
            )
            if (
                user == retailer.account.owner
                or user.is_staff
                or user.is_superuser
                or user.global_roles.filter(role__code="super_admin", account_membership__isnull=True).exists()
            ):
                messages.error(request, "Admin or owner users cannot be assigned as retailer staff.")
                return self.get(request, form=form)
            add_store_staff(
                account=retailer.account,
                store=form.cleaned_data["store"],
                user=user,
                title=form.cleaned_data.get("title") or form.cleaned_data["role_codes"][0].replace("_", " ").title(),
                role_codes=form.cleaned_data["role_codes"],
            )
            messages.success(request, "Store staff member assigned.")
            return redirect("retailers:staff")
        return self.get(request, form=form)

    def get(self, request, *args, **kwargs):
        return self.render_to_response(self.get_context_data(form=kwargs.get("form") or self.get_form()))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        retailer = self.get_retailer()
        show_deleted = self.request.GET.get("show") == "deleted"
        memberships = self.get_staff_memberships_queryset(retailer, include_inactive=True)
        memberships = memberships.filter(is_active=False) if show_deleted else memberships.filter(is_active=True, status="active")
        context.update(
            {
                "page_title": "Store Staff",
                "form": kwargs.get("form") or self.get_form(),
                "staff_memberships": memberships,
                "show_deleted": show_deleted,
            }
        )
        return context


class RetailerApprovalActionView(SuperAdminRequiredMixin, UpdateView):
    model = Retailer
    fields = []
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        retailer = self.get_object()
        approve_retailer(retailer, approver=request.user, notes="Approved from Super Admin panel")
        messages.success(request, "Retailer approved successfully.")
        return redirect("backoffice:module-list", module="retailers")


from django.views.generic import FormView
from django.contrib.auth import login
from apps.accounts.models import Account, AccountMembership
from apps.retailers.forms import RetailerRegistrationForm
from django.contrib import messages

class RetailerRegisterView(FormView):
    template_name = "retailer/register.html"
    form_class = RetailerRegistrationForm
    
    def form_valid(self, form):
        from django.utils.text import slugify
        
        email = form.cleaned_data["email"]
        phone = form.cleaned_data["phone_number"]
        password = form.cleaned_data["password"]
        biz_name = form.cleaned_data["business_name"]
        
        username = generate_unique_username(biz_name)
        
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            phone=phone,
            first_name=biz_name,
            is_active=True
        )
        
        account_slug = slugify(biz_name)
        base_slug = account_slug
        counter = 1
        while Account.objects.filter(slug=account_slug).exists():
            account_slug = f"{base_slug}-{counter}"
            counter += 1
            
        account = Account.objects.create(
            name=biz_name,
            slug=account_slug,
            owner=user,
            country_code="DE",
            currency_code="EUR"
        )
        
        retailer = Retailer.objects.create(
            account=account,
            legal_name=biz_name,
            display_name=biz_name,
            support_email=email,
            support_phone=phone,
            vat_number=form.cleaned_data.get("vat_number") or "",
            business_type=form.cleaned_data.get("business_type") or "",
            business_address=form.cleaned_data.get("business_address") or "",
            business_document=form.cleaned_data.get("business_document"),
            gst_certificate=form.cleaned_data.get("gst_certificate"),
            pan_card=form.cleaned_data.get("pan_card"),
            cancelled_cheque=form.cleaned_data.get("cancelled_cheque"),
            address_proof=form.cleaned_data.get("address_proof"),
            signature=form.cleaned_data.get("signature"),
            msme_certificate=form.cleaned_data.get("msme_certificate"),
            fssai_license=form.cleaned_data.get("fssai_license"),
            status=Retailer.STATUS_APPROVED
        )
        
        membership = AccountMembership.objects.create(
            account=account,
            user=user,
            title="Owner",
            status="active"
        )
        
        store_slug = slugify(f"{biz_name}-store")
        base_store_slug = store_slug
        counter = 1
        while Store.objects.filter(slug=store_slug).exists():
            store_slug = f"{base_store_slug}-{counter}"
            counter += 1
            
        store = Store.objects.create(
            retailer=retailer,
            name=f"{biz_name} Store",
            slug=store_slug,
            contact_email=email,
            contact_phone=phone,
            status=Store.STATUS_ACTIVE
        )
        
        login(self.request, user)

        messages.success(self.request, f"Welcome to CommerceOS, {biz_name}! Your retailer account has been successfully set up.")
        return redirect("retailers:dashboard")


class RetailerAttributesView(RetailerPortalMixin, TemplateView):
    template_name = "retailer/attributes.html"

    def get(self, request, *args, **kwargs):
        return redirect("retailers:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get all active (non-deleted) attributes
        attributes = ProductAttribute.objects.filter(deleted_at__isnull=True).order_by("name")

        context.update({
            "page_title": "Product Attributes",
            "attributes": attributes,
            "total_count": attributes.count(),
        })
        return context


class RetailerProductVariantsView(RetailerPortalMixin, TemplateView):
    template_name = "retailer/product_variants.html"

    def get(self, request, *args, **kwargs):
        return redirect("retailers:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        retailer = self.get_retailer()
        # Show all variants belonging to this retailer, regardless of store membership.
        variants = ProductVariant.objects.filter(
            product__retailer=retailer,
            product__deleted_at__isnull=True,
            deleted_at__isnull=True,
        ).select_related("product").order_by("-created_at")

        variants_data = []
        for variant in variants:
            variants_data.append({
                "variant": variant,
            })

        context.update({
            "page_title": "Device Models",
            "variants": variants_data,
        })
        return context


class RetailerProductVariantCreateView(RetailerPortalMixin, TemplateView):
    template_name = "retailer/product_variant_create.html"

    def get(self, request, *args, **kwargs):
        return redirect("retailers:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        retailer = self.get_retailer()
        # Get products owned by this retailer, not just store-scoped memberships.
        products = Product.objects.filter(
            retailer=retailer,
            deleted_at__isnull=True,
            product_type=Product.TYPE_VARIANT
        ).order_by("name")

        context.update({
            "page_title": "Create Product Variant",
            "products": products,
        })
        return context

    def post(self, request, *args, **kwargs):
        retailer = self.get_retailer()
        try:
            data = json.loads(request.body)
            product_ids = data.get("product_ids", [])
            variant_name = data.get("variant_name", "").strip()

            if not product_ids or len(product_ids) == 0:
                return JsonResponse({"success": False, "message": "Please select at least one product"}, status=400)

            if not variant_name:
                return JsonResponse({"success": False, "message": "Variant name is required"}, status=400)

            # Verify all products belong to this retailer
            products = Product.objects.filter(id__in=product_ids, retailer=retailer, deleted_at__isnull=True)
            if len(products) != len(product_ids):
                return JsonResponse({"success": False, "message": "Invalid products selected"}, status=403)

            created_variants = []
            for product in products:
                # Generate unique SKU
                sku_prefix = f"{product.sku}-{variant_name[:2].upper()}"
                random_suffix = str(uuid.uuid4())[:8].upper()
                sku = f"{sku_prefix}-{random_suffix}"

                variant = ProductVariant.objects.create(
                    product=product,
                    name=variant_name,
                    sku=sku,
                    price=product.price,
                )
                created_variants.append({
                    "id": str(variant.id),
                    "name": variant.name,
                    "sku": variant.sku,
                    "product": product.name,
                })

            return JsonResponse({
                "success": True,
                "message": f"✓ Created {len(created_variants)} variant(s)",
                "variants": created_variants,
            })

        except json.JSONDecodeError:
            return JsonResponse({"success": False, "message": "Invalid request data"}, status=400)
        except Exception as e:
            return JsonResponse({"success": False, "message": f"Error: {str(e)}"}, status=500)


class RetailerVariantDeleteView(RetailerPortalMixin, View):
    def post(self, request, pk):
        retailer = self.get_retailer()
        try:
            variant = ProductVariant.objects.get(
                pk=pk,
                product__retailer=retailer,
                deleted_at__isnull=True
            )
            variant.deleted_at = timezone.now()
            variant.save()
            return JsonResponse({"success": True, "message": "✓ Variant deleted successfully"})
        except ProductVariant.DoesNotExist:
            return JsonResponse({"success": False, "message": "Variant not found"}, status=404)
        except Exception as e:
            return JsonResponse({"success": False, "message": f"Error: {str(e)}"}, status=500)


class RetailerVariantRestoreView(RetailerPortalMixin, View):
    def post(self, request, pk):
        retailer = self.get_retailer()
        try:
            variant = ProductVariant.objects.get(
                pk=pk,
                product__retailer=retailer,
                deleted_at__isnull=False
            )
            variant.deleted_at = None
            variant.save()
            return JsonResponse({"success": True, "message": "✓ Variant restored successfully"})
        except ProductVariant.DoesNotExist:
            return JsonResponse({"success": False, "message": "Variant not found or not deleted"}, status=404)
        except Exception as e:
            return JsonResponse({"success": False, "message": f"Error: {str(e)}"}, status=500)


class RetailerVariantPermanentDeleteView(RetailerPortalMixin, View):
    def post(self, request, pk):
        retailer = self.get_retailer()
        try:
            variant = ProductVariant.objects.get(
                pk=pk,
                product__retailer=retailer
            )
            variant.delete()
            return JsonResponse({"success": True, "message": "✓ Variant permanently deleted"})
        except ProductVariant.DoesNotExist:
            return JsonResponse({"success": False, "message": "Variant not found"}, status=404)
        except Exception as e:
            return JsonResponse({"success": False, "message": f"Error: {str(e)}"}, status=500)


class RetailerStoreRatingListView(RetailerPortalMixin, TemplateView):
    template_name = "retailer/store_ratings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        retailer = self.get_retailer()
        context.update({
            "page_title": "Store Ratings",
            "ratings": StoreRating.objects.filter(store__retailer=retailer).select_related("store").order_by("-created_at"),
            "rating_action_url_name": "retailers:store-rating-action",
            "rating_portal": "retailer",
        })
        return context


class RetailerStoreRatingActionView(RetailerPortalMixin, View):
    VALID_ACTIONS = {"approve", "disapprove", "delete", "restore", "delete-permanent"}

    def post(self, request, action):
        retailer = self.get_retailer()
        if action not in self.VALID_ACTIONS:
            raise Http404("Unknown rating action.")
        ids = request.POST.getlist("ratings")
        ratings = StoreRating.objects.filter(id__in=ids, store__retailer=retailer).select_related("store")
        stores = set(rating.store for rating in ratings)
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
        messages.success(request, f"{ratings.count()} rating(s) updated.")
        return redirect("retailers:store-ratings")
