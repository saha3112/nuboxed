from django.contrib import messages
from django.db import transaction
from django.forms import modelformset_factory
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import CreateView, TemplateView

from apps.catalog.models import Category, ProductVariant
from apps.inventory.forms import (
    CategoryDeliveryRuleForm,
    DeliveryHolidayForm,
    DeliveryLocationForm,
    OfflineSaleForm,
    ProductDeliveryRuleForm,
    StockAdjustmentForm,
    WarehouseForm,
)
from apps.inventory.models import (
    CategoryDeliveryRule,
    DeliveryHoliday,
    DeliveryLocation,
    LowStockAlert,
    OfflineSale,
    ProductDeliveryRule,
    StockItem,
    StockLedger,
    Warehouse,
)
from apps.inventory.services import canonical_stock_items, create_offline_sale, manual_stock_adjustment
from apps.retailers.views import RetailerPortalMixin


class InventoryDashboardView(RetailerPortalMixin, TemplateView):
    template_name = "inventory/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        retailer = self.get_retailer()
        store_ids = self.request.user.get_accessible_store_ids(account=retailer.account)
        stock_queryset = canonical_stock_items(
            StockItem.objects.filter(product__retailer=retailer)
        ).select_related("product", "product__store", "variant", "warehouse", "warehouse__store")
        ledger_queryset = StockLedger.objects.filter(product__retailer=retailer).select_related("product", "warehouse")
        alerts_queryset = LowStockAlert.objects.filter(stock_item__product__retailer=retailer, resolved_at__isnull=True)
        warehouse_queryset = Warehouse.objects.filter(retailer=retailer)
        if store_ids is not None:
            stock_queryset = stock_queryset.filter(product__store_id__in=store_ids)
            ledger_queryset = ledger_queryset.filter(product__store_id__in=store_ids)
            alerts_queryset = alerts_queryset.filter(stock_item__product__store_id__in=store_ids)
            warehouse_queryset = warehouse_queryset.filter(store_id__in=store_ids) | warehouse_queryset.filter(store__isnull=True)
        context.update(
            {
                "page_title": "Inventory Control",
                "warehouses": warehouse_queryset.order_by("name"),
                "stock_items": stock_queryset.order_by("product__name"),
                "ledger_entries": ledger_queryset.order_by("-created_at")[:20],
                "low_stock_alerts": alerts_queryset.order_by("-created_at"),
                "offline_sales": OfflineSale.objects.filter(product__retailer=retailer).order_by("-sold_at")[:10],
                "delivery_locations": DeliveryLocation.objects.filter(retailer=retailer).order_by("priority", "name")[:12],
                "category_delivery_rules": CategoryDeliveryRule.objects.filter(retailer=retailer).select_related("category", "store").order_by("category__name")[:12],
                "product_delivery_rules": ProductDeliveryRule.objects.filter(retailer=retailer).select_related("product", "warehouse").order_by("product__name")[:12],
                "delivery_holidays": DeliveryHoliday.objects.filter(retailer=retailer).order_by("holiday_date", "name")[:12],
            }
        )
        return context


class WarehouseCreateView(RetailerPortalMixin, CreateView):
    template_name = "inventory/form.html"
    form_class = WarehouseForm

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["store"].queryset = self.get_store_queryset(self.get_retailer())
        return form

    def form_valid(self, form):
        warehouse = form.save(commit=False)
        warehouse.retailer = self.get_retailer()
        warehouse.save()
        messages.success(self.request, "Warehouse created.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("inventory:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Create Warehouse"
        return context


class StockAdjustmentCreateView(RetailerPortalMixin, CreateView):
    template_name = "inventory/form.html"
    form_class = StockAdjustmentForm

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        retailer = self.get_retailer()
        form.fields["warehouse"].queryset = Warehouse.objects.filter(retailer=retailer)
        form.fields["product"].queryset = retailer.products.all()
        form.fields["variant"].queryset = ProductVariant.objects.filter(product__retailer=retailer)
        return form

    def form_valid(self, form):
        manual_stock_adjustment(actor=self.request.user, **form.cleaned_data)
        messages.success(self.request, "Stock adjustment recorded.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("inventory:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Manual Stock Adjustment"
        return context


class OfflineSaleCreateView(RetailerPortalMixin, CreateView):
    template_name = "inventory/form.html"
    form_class = OfflineSaleForm

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        retailer = self.get_retailer()
        form.fields["warehouse"].queryset = Warehouse.objects.filter(retailer=retailer)
        form.fields["store"].queryset = self.get_store_queryset(retailer)
        form.fields["product"].queryset = retailer.products.all()
        form.fields["variant"].queryset = ProductVariant.objects.filter(product__retailer=retailer)
        return form

    def form_valid(self, form):
        try:
            create_offline_sale(actor=self.request.user, **form.cleaned_data)
        except ValueError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Offline sale recorded and stock reduced.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("inventory:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Offline Sale Entry"
        return context


class DeliveryLocationCreateView(RetailerPortalMixin, CreateView):
    template_name = "inventory/form.html"
    form_class = DeliveryLocationForm

    def get_formset(self):
        retailer = self.get_retailer()
        store_queryset = self.get_store_queryset(retailer)
        warehouse_queryset = Warehouse.objects.filter(retailer=retailer)
        store_ids = self.request.user.get_accessible_store_ids(account=retailer.account)
        if store_ids is not None:
            warehouse_queryset = warehouse_queryset.filter(store_id__in=store_ids) | warehouse_queryset.filter(store__isnull=True)
        formset_class = modelformset_factory(
            DeliveryLocation,
            form=DeliveryLocationForm,
            extra=1,
            can_delete=False,
        )
        formset = formset_class(
            data=self.request.POST or None,
            queryset=DeliveryLocation.objects.none(),
            prefix="locations",
        )
        for form in formset.forms:
            form.fields["store"].queryset = store_queryset
            form.fields["warehouse"].queryset = warehouse_queryset
        return formset

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        retailer = self.get_retailer()
        store_queryset = self.get_store_queryset(retailer)
        warehouse_queryset = Warehouse.objects.filter(retailer=retailer)
        store_ids = self.request.user.get_accessible_store_ids(account=retailer.account)
        if store_ids is not None:
            warehouse_queryset = warehouse_queryset.filter(store_id__in=store_ids) | warehouse_queryset.filter(store__isnull=True)
        form.fields["store"].queryset = store_queryset
        form.fields["warehouse"].queryset = warehouse_queryset
        return form

    def post(self, request, *args, **kwargs):
        formset = self.get_formset()
        if formset.is_valid():
            retailer = self.get_retailer()
            with transaction.atomic():
                locations = formset.save(commit=False)
                for location in locations:
                    location.retailer = retailer
                    location.save()
            messages.success(self.request, f"{len(locations)} delivery location(s) added.")
            return redirect(self.get_success_url())
        return self.render_to_response(self.get_context_data(formset=formset))

    def get_success_url(self):
        return reverse("inventory:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Add Delivery Locations"
        context["formset"] = kwargs.get("formset") or self.get_formset()
        context["is_multi_delivery_location"] = True
        context["is_delivery_location"] = True
        first_form = context["formset"].forms[0] if context["formset"].forms else None
        context["delivery_country_meta"] = getattr(first_form, "country_meta_json", {})
        context["delivery_country_defaults"] = getattr(first_form, "country_location_defaults_json", {})
        return context


class CategoryDeliveryRuleCreateView(RetailerPortalMixin, CreateView):
    template_name = "inventory/form.html"
    form_class = CategoryDeliveryRuleForm

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        retailer = self.get_retailer()
        form.fields["store"].queryset = self.get_store_queryset(retailer)
        form.fields["category"].queryset = Category.objects.filter(is_active=True).order_by("name")
        return form

    def form_valid(self, form):
        rule = form.save(commit=False)
        rule.retailer = self.get_retailer()
        rule.save()
        messages.success(self.request, "Category delivery rule saved.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("inventory:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Category Delivery Rule"
        return context


class ProductDeliveryRuleCreateView(RetailerPortalMixin, CreateView):
    template_name = "inventory/form.html"
    form_class = ProductDeliveryRuleForm

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        retailer = self.get_retailer()
        product_queryset = retailer.products.all()
        warehouse_queryset = Warehouse.objects.filter(retailer=retailer)
        store_ids = self.request.user.get_accessible_store_ids(account=retailer.account)
        if store_ids is not None:
            product_queryset = product_queryset.filter(store_id__in=store_ids)
            warehouse_queryset = warehouse_queryset.filter(store_id__in=store_ids) | warehouse_queryset.filter(store__isnull=True)
        form.fields["product"].queryset = product_queryset.order_by("name")
        form.fields["warehouse"].queryset = warehouse_queryset
        return form

    def form_valid(self, form):
        rule = form.save(commit=False)
        rule.retailer = self.get_retailer()
        rule.save()
        messages.success(self.request, "Product delivery rule saved.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("inventory:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Product Delivery Rule"
        return context


class DeliveryHolidayCreateView(RetailerPortalMixin, CreateView):
    template_name = "inventory/form.html"
    form_class = DeliveryHolidayForm

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        retailer = self.get_retailer()
        store_queryset = self.get_store_queryset(retailer)
        warehouse_queryset = Warehouse.objects.filter(retailer=retailer)
        store_ids = self.request.user.get_accessible_store_ids(account=retailer.account)
        if store_ids is not None:
            warehouse_queryset = warehouse_queryset.filter(store_id__in=store_ids) | warehouse_queryset.filter(store__isnull=True)
        form.fields["store"].queryset = store_queryset
        form.fields["warehouse"].queryset = warehouse_queryset
        return form

    def form_valid(self, form):
        holiday = form.save(commit=False)
        holiday.retailer = self.get_retailer()
        holiday.save()
        messages.success(self.request, "Delivery holiday saved.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("inventory:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Delivery Holiday"
        return context
