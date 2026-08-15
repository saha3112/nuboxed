from django import forms
from django.utils import timezone
from django.forms import BaseModelFormSet
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import OrderedDict

from apps.retailers.forms import COUNTRY_LOCATION_DEFAULTS, load_country_choices

from apps.inventory.models import (
    CategoryDeliveryRule,
    DeliveryLocation,
    OfflineSale,
    ProductDeliveryRule,
    StockAdjustment,
    Warehouse,
)
from apps.catalog.models import Brand, Product, ProductVariant


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        exclude = ("retailer", "created_at", "updated_at")

class StockAdjustmentForm(forms.ModelForm):
    class Meta:
        model = StockAdjustment
        exclude = ("created_by", "created_at", "updated_at")


class OfflineSaleForm(forms.ModelForm):
    device_type = forms.ChoiceField(label="Device type", choices=(("", "Select device type"), ("smartphone", "Smartphone"), ("tablet", "Tablet"), ("laptop", "Laptop")), required=True)
    brand = forms.ModelChoiceField(
        label="Brand",
        queryset=Brand.objects.none(),
        required=True,
        empty_label="Select brand",
    )
    sold_at = forms.DateTimeField(
        label="Sold at",
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"],
        widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
    )
    delivery_location = forms.ModelChoiceField(
        label="Delivery Location / PIN coverage",
        queryset=DeliveryLocation.objects.none(),
        required=False,
        empty_label="Select PIN coverage (optional)",
    )
    delivery_pincode = forms.ChoiceField(label="Delivery PIN code", required=False, choices=())

    class Meta:
        model = OfflineSale
        exclude = ("created_by", "total_amount", "created_at", "updated_at", "warehouse")

    def __init__(self, *args, retailer=None, store=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.retailer = retailer
        self.store = store
        if retailer:
            brand_qs = Brand.objects.filter(
                products__retailer=retailer,
                products__is_active=True,
                products__deleted_at__isnull=True,
            )
            if store:
                brand_qs = brand_qs.filter(products__store=store)
            device_type = self.data.get(self.add_prefix("device_type")) or self.initial.get("device_type")
            if device_type:
                brand_qs = brand_qs.filter(products__category__name__icontains=device_type)
            self.fields["brand"].queryset = brand_qs.distinct().order_by("name")
            brand_id = self.data.get(self.add_prefix("brand")) or self.initial.get("brand")
            product_qs = Product.objects.none()
            if device_type and brand_id:
                product_qs = Product.objects.filter(retailer=retailer, is_active=True, deleted_at__isnull=True)
                if store:
                    product_qs = product_qs.filter(store=store)
                product_qs = product_qs.filter(brand_id=brand_id, category__name__icontains=device_type)
            self.fields["product"].queryset = product_qs.order_by("name")
            product_id = self.data.get(self.add_prefix("product")) or self.initial.get("product")
            self.fields["variant"].queryset = ProductVariant.objects.filter(
                product_id=product_id, deleted_at__isnull=True
            ).order_by("name") if product_id else ProductVariant.objects.none()
            self.fields["store"].queryset = retailer.stores.filter(is_active=True, status="active")
            if store:
                self.fields["store"].queryset = self.fields["store"].queryset.filter(pk=store.pk)
        self.fields["sold_at"].initial = self.initial.get("sold_at") or timezone.localtime(timezone.now()).strftime("%Y-%m-%dT%H:%M")
        self.fields["store"].label = "Store (auto-selected)"
        if retailer:
            self.fields["delivery_location"].queryset = DeliveryLocation.objects.filter(
                retailer=retailer, store=store, is_active=True
            ).order_by("priority", "name")
            self.fields["delivery_location"].label_from_instance = lambda location: (
                f"{location.postal_code} — {location.name}" if location.postal_code else location.name
            )
            pin_choices = []
            for location in self.fields["delivery_location"].queryset:
                for pin in re.split(r"[,;\n]+", location.postal_code or ""):
                    pin = pin.strip()
                    if pin:
                        detail = (location.pin_details or {}).get(pin, {})
                        # Never use the grouped location name as the first
                        # fallback: it makes every PIN option look identical
                        # before the browser finishes the PIN lookup.
                        areas = detail.get("post_offices") or detail.get("area_name") or f"PIN {pin} coverage"
                        if isinstance(areas, list):
                            areas = ", ".join(areas)
                        city = detail.get("city") or location.city
                        state = detail.get("state") or location.state
                        country = detail.get("country") or location.country_code
                        latitude = detail.get("latitude") or location.latitude
                        longitude = detail.get("longitude") or location.longitude
                        meta = " · ".join(filter(None, [
                            str(areas),
                            f"City: {city}" if city else "",
                            f"State: {state}" if state else "",
                            f"Country: {country}" if country else "",
                            f"Lat: {latitude}" if latitude else "",
                            f"Long: {longitude}" if longitude else "",
                        ]))
                        label = f"{pin} — {meta}"
                        pin_choices.append((f"{location.pk}::{pin}", label))
            self.fields["delivery_pincode"].choices = [("", "Select delivery PIN code")] + pin_choices
            selected_pin = getattr(self.instance, "selected_pincode", "") if self.instance and self.instance.pk else ""
            for value, label in pin_choices:
                if selected_pin and label.startswith(f"{selected_pin} —"):
                    self.fields["delivery_pincode"].initial = value
                    break
        field_order = ["is_active", "store", "delivery_pincode", "device_type", "brand", "product", "variant", "quantity", "unit_price", "sold_at", "note"]
        self.fields = OrderedDict((name, self.fields[name]) for name in field_order if name in self.fields)

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get("product")
        variant = cleaned.get("variant")
        store = cleaned.get("store")
        quantity = cleaned.get("quantity")
        brand = cleaned.get("brand")
        delivery_location = cleaned.get("delivery_location")
        delivery_pincode = cleaned.get("delivery_pincode")
        if delivery_pincode:
            try:
                location_id, selected_pin = delivery_pincode.split("::", 1)
                location = DeliveryLocation.objects.filter(pk=location_id, retailer=self.retailer, is_active=True).first()
                if not location:
                    self.add_error("delivery_pincode", "Select a valid delivery PIN code.")
                else:
                    cleaned["delivery_location"] = location
                    cleaned["selected_pincode"] = selected_pin
            except ValueError:
                self.add_error("delivery_pincode", "Select a valid delivery PIN code.")

        if quantity is not None and quantity <= 0:
            self.add_error("quantity", "Quantity must be greater than zero.")
        if product and product.variants.exists() and not variant:
            self.add_error("variant", "Select the exact product variant for this sale.")
        if product and variant and variant.product_id != product.id:
            self.add_error("variant", "The selected variant does not belong to this product.")
        if product and brand and product.brand_id != brand.id:
            self.add_error("product", "Select a product from the selected brand.")
        if delivery_location and store and delivery_location.store_id != store.id:
            self.add_error("delivery_location", "Select a delivery location assigned to this store.")
        if product and product.store_id and store and product.store_id != store.id:
            self.add_error("store", "Select the store assigned to this product.")
        return cleaned


class DeliveryLocationForm(forms.ModelForm):
    country_code = forms.ChoiceField(label="Country", choices=())
    # The geocoding service may return 7+ decimal places, while the model
    # stores coordinates at 6 decimal places. Keep the input permissive and
    # normalize it in clean_* before ModelForm validation reaches the model.
    latitude = forms.CharField(required=False, label="Latitude")
    longitude = forms.CharField(required=False, label="Longitude")

    class Meta:
        model = DeliveryLocation
        exclude = ("retailer", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].label = "Location / Area name"
        self.fields["name"].help_text = "This name is shown in delivery rules. It can be filled automatically from the PIN code(s)."
        self.fields["name"].widget.attrs.update({"placeholder": "e.g. Hooghly Area / Bamunari & Nearby PINs"})
        self.fields["postal_code"].label = "Exact PIN code(s)"
        self.fields["postal_code"].help_text = "Enter one or more exact PIN codes. Separate multiple codes with commas or new lines. Example: 110001, 110002, 110003"
        self.fields["postal_code"].widget = forms.Textarea(attrs={"rows": 2, "placeholder": "e.g. 110001, 110002, 110003"})
        self.fields["pin_details"].widget = forms.HiddenInput()
        self.fields["postal_code_prefix"].label = "PIN prefix for a wider area (optional)"
        self.fields["postal_code_prefix"].help_text = "Enter the starting digits to cover a wider area. Example: 110 covers 110001, 110002, and other PINs beginning with 110."

        self.country_choices, self.country_meta = load_country_choices()
        self.fields["country_code"].choices = self.country_choices
        self.fields["country_code"].widget.attrs.update({"class": "ra-input ra-country-select", "data-country-select": "true"})
        for field_name in self.fields:
            self.fields[field_name].widget.attrs.setdefault("class", "ra-input")
        self.country_location_defaults = self._country_location_payload()
        self.country_meta_json = self.country_meta
        self.country_location_defaults_json = self.country_location_defaults

    def _country_location_payload(self):
        label_map = {
            "AE": {"state": "Emirate", "city": "City", "postal_code": "Postal Code", "postal_code_prefix": "Postal Code Prefix"},
            "AU": {"state": "State / Territory", "city": "Suburb / City", "postal_code": "Postcode", "postal_code_prefix": "Postcode Prefix"},
            "BD": {"state": "Division", "city": "City / District", "postal_code": "Postal Code", "postal_code_prefix": "Postal Code Prefix"},
            "DE": {"state": "Federal State", "city": "City", "postal_code": "Postal Code", "postal_code_prefix": "Postal Code Prefix"},
            "GB": {"state": "Region / County", "city": "Town / City", "postal_code": "Postcode", "postal_code_prefix": "Postcode Prefix"},
            "IN": {"state": "State / Union Territory", "city": "City", "postal_code": "PIN Code", "postal_code_prefix": "PIN Prefix"},
            "US": {"state": "State", "city": "City", "postal_code": "ZIP Code", "postal_code_prefix": "ZIP Prefix"},
        }
        payload = {}
        for code, meta in self.country_meta.items():
            payload[code] = {
                "labels": label_map.get(code, {"state": "State / Province / Region", "city": "City", "postal_code": "Postal Code", "postal_code_prefix": "Postal Code Prefix"}),
                "visibility": {
                    "state": code not in {"HK", "SG", "QA", "KW", "BH"},
                    "city": True,
                    "postal_code": code not in {"HK", "QA", "KW"},
                    "postal_code_prefix": code not in {"HK", "QA", "KW"},
                },
                "defaults": COUNTRY_LOCATION_DEFAULTS.get(code, {}),
            }
        return payload

    def clean_postal_code(self):
        value = (self.cleaned_data.get("postal_code") or "").replace("\r\n", "\n")
        values = []
        seen = set()
        for raw in re.split(r"[,;\n]+", value):
            code = "".join(char for char in raw.strip().upper() if char.isalnum())
            if code and code not in seen:
                values.append(code)
                seen.add(code)
        return ",".join(values)

    def clean_postal_code_prefix(self):
        value = (self.cleaned_data.get("postal_code_prefix") or "").replace("\r\n", "\n")
        values = []
        seen = set()
        for raw in re.split(r"[,;\n]+", value):
            code = "".join(char for char in raw.strip().upper() if char.isalnum())
            if code and code not in seen:
                values.append(code)
                seen.add(code)
        return ",".join(values)

    def _clean_coordinate(self, field_name, minimum, maximum):
        raw_value = (self.cleaned_data.get(field_name) or "").strip()
        if not raw_value:
            return None
        try:
            value = Decimal(raw_value).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, TypeError, ValueError):
            raise forms.ValidationError("Enter a valid coordinate.")
        if value < minimum or value > maximum:
            raise forms.ValidationError(f"Enter a value between {minimum} and {maximum}.")
        return value

    def clean_latitude(self):
        return self._clean_coordinate("latitude", Decimal("-90"), Decimal("90"))

    def clean_longitude(self):
        return self._clean_coordinate("longitude", Decimal("-180"), Decimal("180"))


class DeliveryLocationFormSet(BaseModelFormSet):
    """Validate each card as one location and keep exact PIN coverage unique."""

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        seen_codes = {}
        for index, form in enumerate(self.forms, start=1):
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            country = form.cleaned_data.get("country_code") or ""
            for code in (form.cleaned_data.get("postal_code") or "").split(","):
                code = code.strip().upper()
                if not code:
                    continue
                key = (country, code)
                if key in seen_codes:
                    form.add_error("postal_code", f"PIN {code} is already used in Location {seen_codes[key]}. Keep each PIN in one location card.")
                else:
                    seen_codes[key] = index


class CategoryDeliveryRuleForm(forms.ModelForm):
    class Meta:
        model = CategoryDeliveryRule
        exclude = ("retailer", "created_at", "updated_at")


class ProductDeliveryRuleForm(forms.ModelForm):
    class Meta:
        model = ProductDeliveryRule
        exclude = ("retailer", "created_at", "updated_at")
