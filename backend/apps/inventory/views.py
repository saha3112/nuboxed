from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.forms import modelformset_factory
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import CreateView, TemplateView, UpdateView, View

from apps.catalog.models import Brand, Category, Product, ProductVariant
from apps.inventory.forms import (
    CategoryDeliveryRuleForm,
    DeliveryLocationForm,
    DeliveryLocationFormSet,
    OfflineSaleForm,
    ProductDeliveryRuleForm,
    StockAdjustmentForm,
    WarehouseForm,
)
from apps.inventory.models import (
    CategoryDeliveryRule,
    DeliveryLocation,
    LowStockAlert,
    OfflineSale,
    ProductDeliveryRule,
    StockItem,
    StockLedger,
    Warehouse,
)
from apps.inventory.services import (
    canonical_stock_items, create_offline_sale, manual_stock_adjustment,
    offline_sales_enabled, set_offline_sales_enabled,
    set_offline_sale_active,
)
from apps.retailers.views import RetailerPortalMixin
from apps.inventory.delivery import normalize_postal_code
import requests
import re


class InventoryDashboardView(RetailerPortalMixin, TemplateView):
    template_name = "inventory/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        retailer = self.get_retailer()
        store_ids = self.request.user.get_accessible_store_ids(account=retailer.account)
        stock_queryset = canonical_stock_items(
            StockItem.objects.filter(product__retailer=retailer, product__deleted_at__isnull=True)
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
                "stock_totals": {
                    "on_hand": stock_queryset.aggregate(value=Sum("on_hand_quantity"))["value"] or 0,
                    "reserved": stock_queryset.aggregate(value=Sum("reserved_quantity"))["value"] or 0,
                    "damaged": stock_queryset.aggregate(value=Sum("damaged_quantity"))["value"] or 0,
                },
                "ledger_entries": ledger_queryset.order_by("-created_at")[:20],
                "low_stock_alerts": alerts_queryset.order_by("-created_at"),
                "offline_sales": OfflineSale.objects.filter(product__retailer=retailer, is_active=True).select_related("delivery_location").order_by("-sold_at")[:10],
                "deleted_offline_sales": OfflineSale.objects.filter(product__retailer=retailer, is_active=False).select_related("delivery_location").order_by("-sold_at")[:10],
                "delivery_locations": DeliveryLocation.objects.filter(retailer=retailer).order_by("priority", "name")[:12],
                "category_delivery_rules": CategoryDeliveryRule.objects.filter(retailer=retailer).select_related("category", "store").order_by("category__name")[:12],
                "product_delivery_rules": ProductDeliveryRule.objects.filter(retailer=retailer).select_related("product", "warehouse").order_by("product__name")[:12],
            }
        )
        return context


class DeliveryLocationsRulesView(RetailerPortalMixin, TemplateView):
    template_name = "inventory/delivery_locations.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        retailer = self.get_retailer()
        locations = DeliveryLocation.objects.filter(retailer=retailer).select_related("store", "warehouse").order_by("priority", "name")
        context.update({
            "page_title": "Pincode & ETA Rules",
            "delivery_locations": locations.filter(is_active=True),
            "deleted_delivery_locations": locations.filter(is_active=False),
        })
        return context


class DeliveryLocationUpdateView(RetailerPortalMixin, UpdateView):
    template_name = "inventory/form.html"
    form_class = DeliveryLocationForm
    model = DeliveryLocation

    def get_queryset(self):
        return DeliveryLocation.objects.filter(retailer=self.get_retailer())

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["store"].queryset = self.get_store_queryset(self.get_retailer()).filter(status="active", is_active=True).order_by("name")
        form.fields["store"].required = True
        form.fields.pop("warehouse", None)
        return form

    def form_valid(self, form):
        form.instance.retailer = self.get_retailer()
        response = super().form_valid(form)
        messages.success(self.request, "Delivery location updated successfully.")
        return response

    def get_success_url(self):
        return reverse("inventory:delivery-locations")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"page_title": "Edit Delivery Location", "is_delivery_location": True, "is_multi_delivery_location": False})
        return context


class DeliveryLocationActionView(RetailerPortalMixin, View):
    def post(self, request, pk, action, *args, **kwargs):
        location = get_object_or_404(DeliveryLocation, pk=pk, retailer=self.get_retailer())
        if action == "delete":
            location.is_active = False
            location.save(update_fields=["is_active", "updated_at"])
            messages.success(request, "Delivery location moved to trash.")
        elif action == "restore":
            location.is_active = True
            location.save(update_fields=["is_active", "updated_at"])
            messages.success(request, "Delivery location restored.")
        elif action == "delete-permanent":
            if location.is_active:
                messages.error(request, "Move the location to trash before permanently deleting it.")
            else:
                location.delete()
                messages.success(request, "Delivery location permanently deleted.")
        else:
            messages.error(request, "Unsupported delivery location action.")
        return redirect("inventory:delivery-locations")


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

    def dispatch(self, request, *args, **kwargs):
        self.portal_user = self.get_portal_user()
        if self.portal_user and not offline_sales_enabled(self.get_retailer()):
            messages.error(request, "Offline Sales is disabled for this retailer. Enable it from Offline Sales Settings.")
            return redirect("inventory:offline-sales-settings")
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        retailer = self.get_retailer()
        store = getattr(self, "object", None) and self.object.store or self.get_store_queryset(retailer).filter(status="active", is_active=True).order_by("-is_active", "name").first()
        initial = {"brand": self.object.product.brand_id, "delivery_location": self.object.delivery_location_id} if getattr(self, "object", None) else None
        form = self.form_class(self.request.POST or None, instance=getattr(self, "object", None), retailer=retailer, store=store, initial=initial)
        form.fields["store"].initial = store.pk if store else None
        if getattr(self, "object", None):
            form.fields["product"].disabled = True
            form.fields["variant"].disabled = True
            form.fields["quantity"].disabled = True
            form.fields["brand"].disabled = True
        return form

    def form_valid(self, form):
        try:
            retailer = self.get_retailer()
            store = form.cleaned_data["store"]
            product = form.cleaned_data["product"]
            variant = form.cleaned_data.get("variant")
            stock_item = StockItem.objects.filter(
                product=product, variant=variant, warehouse__retailer=retailer,
            ).filter(warehouse__store=store).select_related("warehouse").first()
            if not stock_item:
                stock_item = StockItem.objects.filter(
                    product=product, variant=variant, warehouse__retailer=retailer,
                    warehouse__store__isnull=True,
                ).select_related("warehouse").first()
            if not stock_item:
                form.add_error(None, "No warehouse stock record exists for this product and store.")
                return self.form_invalid(form)
            sale_data = dict(form.cleaned_data)
            sale_data["warehouse"] = stock_item.warehouse
            sale_data.pop("brand", None)
            sale_data.pop("delivery_pincode", None)
            create_offline_sale(actor=self.request.user, **sale_data)
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
        context["is_offline_sale"] = True
        return context


class OfflineSaleOptionsView(RetailerPortalMixin, View):
    def get(self, request, *args, **kwargs):
        retailer = self.get_retailer()
        store = self.get_store_queryset(retailer).filter(status="active", is_active=True).first()
        brand_id = request.GET.get("brand_id")
        product_id = request.GET.get("product_id")
        device_type = request.GET.get("device_type", "").strip().lower()
        if product_id:
            variants = ProductVariant.objects.filter(product_id=product_id, product__retailer=retailer, deleted_at__isnull=True).order_by("name")
            return JsonResponse({"variants": [{"id": str(v.pk), "name": v.name, "sku": v.sku} for v in variants]})
        products = Product.objects.filter(retailer=retailer, is_active=True, deleted_at__isnull=True)
        if store:
            products = products.filter(store=store)
        if device_type:
            products = products.filter(category__name__icontains=device_type)
        if brand_id:
            products = products.filter(brand_id=brand_id)
        if not brand_id:
            brands = Brand.objects.filter(products__in=products).distinct().order_by("name")
            return JsonResponse({"brands": [{"id": str(b.pk), "name": b.name} for b in brands]})
        return JsonResponse({"products": [{"id": str(p.pk), "name": p.name, "sku": p.sku} for p in products.order_by("name")]})


class OfflineSaleUpdateView(RetailerPortalMixin, UpdateView):
    template_name = "inventory/form.html"
    form_class = OfflineSaleForm
    model = OfflineSale

    def get_queryset(self):
        return OfflineSale.objects.filter(product__retailer=self.get_retailer(), is_active=True).select_related("product", "store", "delivery_location")

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
        return redirect("inventory:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"page_title": "Edit Offline Sale", "is_offline_sale": True, "retailer": self.get_retailer(), "stores": self.get_store_queryset(self.get_retailer()), "primary_store": self.object.store})
        return context


class OfflineSaleActionView(RetailerPortalMixin, View):
    def post(self, request, pk, action, *args, **kwargs):
        sale = get_object_or_404(OfflineSale, pk=pk, product__retailer=self.get_retailer())
        try:
            if action == "delete":
                set_offline_sale_active(sale, False, actor=getattr(self, "portal_user", request.user))
                messages.success(request, "Offline sale moved to trash.")
            elif action == "restore":
                set_offline_sale_active(sale, True, actor=getattr(self, "portal_user", request.user))
                messages.success(request, "Offline sale restored and stock reserved again.")
            elif action == "delete-permanent":
                if sale.is_active:
                    messages.error(request, "Move the sale to trash before permanently deleting it.")
                else:
                    sale.delete()
                    messages.success(request, "Offline sale permanently deleted.")
            else:
                messages.error(request, "Unsupported offline sale action.")
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect("inventory:dashboard")


class OfflineSalesSettingsView(RetailerPortalMixin, View):
    template_name = "inventory/offline_sales_settings.html"

    def get(self, request, *args, **kwargs):
        retailer = self.get_retailer()
        sales = OfflineSale.objects.filter(product__retailer=retailer).select_related("store", "product", "created_by").order_by("-sold_at")[:8]
        return self.render_page(request, retailer, sales)

    def post(self, request, *args, **kwargs):
        retailer = self.get_retailer()
        enabled = request.POST.get("enabled") == "on"
        set_offline_sales_enabled(retailer, enabled, actor=getattr(self, "portal_user", request.user))
        messages.success(request, f"Offline Sales {('enabled' if enabled else 'disabled')} successfully.")
        return redirect("inventory:offline-sales-settings")

    def render_page(self, request, retailer, sales):
        return render(request, self.template_name, {
            "page_title": "Offline Sales Settings",
            "retailer": retailer,
            "stores": self.get_store_queryset(retailer),
            "primary_store": self.get_primary_store(retailer),
            "offline_sales_enabled": offline_sales_enabled(retailer),
            "offline_sales": sales,
        })


class DeliveryLocationCreateView(RetailerPortalMixin, CreateView):
    template_name = "inventory/form.html"
    form_class = DeliveryLocationForm

    @staticmethod
    def _hide_warehouse_field(form):
        # Retailers define delivery coverage by address/store. Warehouse
        # assignment remains an internal inventory concern and is not part of
        # the retailer's Add Delivery Locations form.
        form.fields.pop("warehouse", None)
        return form

    def get_formset(self):
        retailer = self.get_retailer()
        store_queryset = self.get_store_queryset(retailer).filter(
            status="active", is_active=True
        ).order_by("name")
        default_store = store_queryset.first()
        formset_class = modelformset_factory(
            DeliveryLocation,
            form=DeliveryLocationForm,
            formset=DeliveryLocationFormSet,
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
            form.fields["store"].required = True
            if default_store and not form.initial.get("store"):
                form.initial["store"] = default_store.pk
                form.fields["store"].initial = default_store.pk
                if default_store.country_code:
                    form.fields["country_code"].initial = default_store.country_code
            self._hide_warehouse_field(form)
        empty_form = formset.empty_form
        empty_form.fields["store"].queryset = store_queryset
        empty_form.fields["store"].required = True
        if default_store:
            empty_form.initial["store"] = default_store.pk
            empty_form.fields["store"].initial = default_store.pk
            if default_store.country_code:
                empty_form.fields["country_code"].initial = default_store.country_code
        self._hide_warehouse_field(empty_form)
        formset.active_store = default_store
        return formset

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        retailer = self.get_retailer()
        store_queryset = self.get_store_queryset(retailer).filter(status="active", is_active=True).order_by("name")
        form.fields["store"].queryset = store_queryset
        form.fields["store"].required = True
        if store_queryset.exists():
            form.initial["store"] = store_queryset.first().pk
            form.fields["store"].initial = store_queryset.first().pk
            if store_queryset.first().country_code:
                form.fields["country_code"].initial = store_queryset.first().country_code
        self._hide_warehouse_field(form)
        return form

    def post(self, request, *args, **kwargs):
        # The custom formset flow does not call CreateView.post(), which
        # normally initializes this attribute before context rendering.
        self.object = None
        formset = self.get_formset()
        if not getattr(formset, "active_store", None):
            return self.render_to_response(self.get_context_data(formset=formset, no_active_store=True))
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
        # RetailerPortalMixin eventually calls CreateView's context builder,
        # which expects the object attribute even when a formset is invalid.
        self.object = None
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Add Delivery Locations"
        context["formset"] = kwargs.get("formset") or self.get_formset()
        context["is_multi_delivery_location"] = True
        context["is_delivery_location"] = True
        context["no_active_store"] = kwargs.get("no_active_store", False) or not getattr(context["formset"], "active_store", None)
        context["active_delivery_store"] = getattr(context["formset"], "active_store", None)
        first_form = context["formset"].forms[0] if context["formset"].forms else None
        context["delivery_country_meta"] = getattr(first_form, "country_meta_json", {})
        context["delivery_country_defaults"] = getattr(first_form, "country_location_defaults_json", {})
        return context


class DeliveryPostalLookupView(RetailerPortalMixin, View):
    """Return address metadata for one or more retailer-entered PIN codes."""

    def get(self, request, *args, **kwargs):
        country = (request.GET.get("country") or "").strip().upper()
        if len(country) != 2:
            country_match = re.search(r"\(([A-Z]{2})\)$", country)
            country = country_match.group(1) if country_match else {"INDIA": "IN", "BANGLADESH": "BD", "GERMANY": "DE"}.get(country, country)
        raw_codes = request.GET.get("pincodes") or request.GET.get("pincode") or ""
        if len(country) != 2 or not country.isalpha():
            return JsonResponse({"ok": False, "message": "Select a valid country first."}, status=400)

        codes = []
        seen = set()
        for raw in re.split(r"[,;\n]+", raw_codes):
            code = normalize_postal_code(raw)
            if code and code not in seen:
                codes.append(code)
                seen.add(code)
        codes = codes[:8]
        if not codes:
            return JsonResponse({"ok": False, "message": "Enter at least one PIN code."}, status=400)

        results = []
        for code in codes:
            result = None
            # India Post is the authoritative source for Indian PIN codes;
            # it also covers valid PINs that are missing from generic global
            # postal APIs (for example 712250).
            if country == "IN":
                try:
                    india_response = requests.get(
                        f"https://api.postalpincode.in/pincode/{code}",
                        headers={"Accept": "application/json", "User-Agent": "Nuboxed delivery location lookup"},
                        timeout=8,
                    )
                    india_payload = india_response.json() if india_response.status_code == 200 else []
                    offices = (india_payload[0].get("PostOffice") or []) if india_payload else []
                    if offices:
                        first = offices[0]
                        office_names = []
                        for office in offices:
                            name = (office.get("Name") or "").strip()
                            if name and name not in office_names:
                                office_names.append(name)
                        result = {
                            "pincode": code,
                            "city": first.get("District") or first.get("Block") or "",
                            "state": first.get("State") or "",
                            "state_code": "",
                            "country": first.get("Country") or "India",
                            "country_code": "IN",
                            "post_offices": office_names,
                            "latitude": "",
                            "longitude": "",
                        }
                except (requests.RequestException, ValueError, IndexError, AttributeError):
                    pass

                # India Post supplies the postal truth; geocoding supplies
                # the map point for the whole PIN area.
                if result:
                    try:
                        geo = requests.get(
                            "https://nominatim.openstreetmap.org/search",
                            params={"postalcode": code, "countrycodes": "in", "format": "jsonv2", "addressdetails": 1, "limit": 1},
                            headers={"Accept": "application/json", "User-Agent": "Nuboxed delivery location lookup"},
                            timeout=8,
                        )
                        geo_places = geo.json() if geo.status_code == 200 else []
                        if geo_places:
                            result["latitude"] = geo_places[0].get("lat", "")
                            result["longitude"] = geo_places[0].get("lon", "")
                            address = geo_places[0].get("address") or {}
                            result["city"] = result["city"] or address.get("city") or address.get("town") or address.get("municipality") or ""
                            result["state"] = result["state"] or address.get("state") or address.get("state_district") or ""
                    except (requests.RequestException, ValueError, IndexError):
                        pass

            try:
                for _attempt in range(2):
                    if result:
                        break
                    response = requests.get(
                        f"https://api.zippopotam.us/{country}/{code}",
                        headers={"Accept": "application/json", "User-Agent": "Nuboxed delivery location lookup"},
                        timeout=5,
                    )
                    if response.status_code == 200:
                        payload = response.json()
                        places = payload.get("places") or []
                        if places:
                            place = places[0]
                            result = {
                                "pincode": code,
                                "city": place.get("place name", ""),
                                "state": place.get("state", ""),
                                "state_code": place.get("state abbreviation", ""),
                                "country": payload.get("country", ""),
                                "country_code": country,
                                "latitude": place.get("latitude", ""),
                                "longitude": place.get("longitude", ""),
                            }
                            break
            except (requests.RequestException, ValueError):
                pass

            # Provider fallback for valid postal codes not covered by
            # Zippopotam.us or when that service is temporarily unavailable.
            if result is None:
                try:
                    fallback = requests.get(
                        "https://nominatim.openstreetmap.org/search",
                        params={"postalcode": code, "countrycodes": country.lower(), "format": "jsonv2", "addressdetails": 1, "limit": 1},
                        headers={"Accept": "application/json", "User-Agent": "Nuboxed delivery location lookup"},
                        timeout=6,
                    )
                    places = fallback.json() if fallback.status_code == 200 else []
                    if places:
                        place = places[0]
                        address = place.get("address") or {}
                        result = {
                            "pincode": code,
                            "city": address.get("city") or address.get("town") or address.get("village") or address.get("municipality") or "",
                            "state": address.get("state") or address.get("state_district") or "",
                            "state_code": address.get("state_code") or "",
                            "country": address.get("country") or "",
                            "country_code": country,
                            "latitude": place.get("lat", ""),
                            "longitude": place.get("lon", ""),
                        }
                except (requests.RequestException, ValueError):
                    pass

            if result:
                results.append(result)

        return JsonResponse({
            "ok": bool(results),
            "results": results,
            "found": len(results),
            "requested": len(codes),
            "message": "" if results else "PIN details could not be found. You can enter the location manually.",
        })


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
