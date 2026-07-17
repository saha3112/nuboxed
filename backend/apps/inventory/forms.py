from django import forms
import json

from apps.retailers.forms import COUNTRY_LOCATION_DEFAULTS, load_country_choices

from apps.inventory.models import (
    CategoryDeliveryRule,
    DeliveryHoliday,
    DeliveryLocation,
    OfflineSale,
    ProductDeliveryRule,
    StockAdjustment,
    Warehouse,
)


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        exclude = ("retailer", "created_at", "updated_at")


class StockAdjustmentForm(forms.ModelForm):
    class Meta:
        model = StockAdjustment
        exclude = ("created_by", "created_at", "updated_at")


class OfflineSaleForm(forms.ModelForm):
    class Meta:
        model = OfflineSale
        exclude = ("created_by", "total_amount", "created_at", "updated_at")

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get("product")
        variant = cleaned.get("variant")
        store = cleaned.get("store")
        warehouse = cleaned.get("warehouse")
        quantity = cleaned.get("quantity")

        if quantity is not None and quantity <= 0:
            self.add_error("quantity", "Quantity must be greater than zero.")
        if product and product.variants.exists() and not variant:
            self.add_error("variant", "Select the exact product variant for this sale.")
        if product and variant and variant.product_id != product.id:
            self.add_error("variant", "The selected variant does not belong to this product.")
        if product and product.store_id and store and product.store_id != store.id:
            self.add_error("store", "Select the store assigned to this product.")
        if warehouse and warehouse.store_id and store and warehouse.store_id != store.id:
            self.add_error("warehouse", "This warehouse belongs to a different store.")
        return cleaned


class DeliveryLocationForm(forms.ModelForm):
    country_code = forms.ChoiceField(label="Country", choices=())

    class Meta:
        model = DeliveryLocation
        exclude = ("retailer", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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


class CategoryDeliveryRuleForm(forms.ModelForm):
    class Meta:
        model = CategoryDeliveryRule
        exclude = ("retailer", "created_at", "updated_at")


class ProductDeliveryRuleForm(forms.ModelForm):
    class Meta:
        model = ProductDeliveryRule
        exclude = ("retailer", "created_at", "updated_at")


class DeliveryHolidayForm(forms.ModelForm):
    class Meta:
        model = DeliveryHoliday
        exclude = ("retailer", "created_at", "updated_at")
