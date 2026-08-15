from django import forms

from apps.catalog.models import Category, Product, ProductVariant
from apps.settings_app.models import SaleCountdownSetting


class SaleCountdownSettingForm(forms.ModelForm):
    product = forms.ModelChoiceField(queryset=Product.objects.none(), required=False, empty_label="Select product (optional)")
    variant = forms.ModelChoiceField(queryset=ProductVariant.objects.none(), required=False, empty_label="Select variant (optional)")
    variants = forms.ModelMultipleChoiceField(
        queryset=ProductVariant.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "sale-countdown-variants"}),
        label="Choose variants",
    )
    all_variants = forms.BooleanField(required=False, initial=True, label="Apply to all variants")
    discount_percentage = forms.DecimalField(
        label="Discount %",
        min_value=0,
        max_value=100,
        required=False,
        initial=0,
        decimal_places=2,
        max_digits=5,
        widget=forms.NumberInput(attrs={"class": "ra-input", "min": "0", "max": "100", "step": "1", "inputmode": "numeric"}),
    )
    starts_at = forms.SplitDateTimeField(
        required=False, input_date_formats=["%Y-%m-%d"], input_time_formats=["%H:%M", "%H:%M:%S"],
        widget=forms.SplitDateTimeWidget(date_format="%Y-%m-%d", time_format="%H:%M", date_attrs={"type":"date","class":"ra-input sale-countdown-date","aria-label":"Start date"}, time_attrs={"type":"time","step":"60","class":"ra-input sale-countdown-time","aria-label":"Start time"}),
    )
    ends_at = forms.SplitDateTimeField(
        required=False,
        input_date_formats=["%Y-%m-%d"],
        input_time_formats=["%H:%M", "%H:%M:%S"],
        widget=forms.SplitDateTimeWidget(
            date_format="%Y-%m-%d",
            time_format="%H:%M",
            date_attrs={"type": "date", "class": "ra-input sale-countdown-date", "aria-label": "End date"},
            time_attrs={"type": "time", "step": "60", "class": "ra-input sale-countdown-time", "aria-label": "End time"},
        ),
    )

    class Meta:
        model = SaleCountdownSetting
        fields = ("name", "retailer", "category", "product", "variant", "variants", "all_variants", "discount_percentage", "message", "starts_at", "ends_at", "is_active")
        widgets = {
            "name": forms.TextInput(attrs={"class": "ra-input", "placeholder": "e.g. Independence Day Laptop Sale"}),
        }

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("starts_at"), cleaned.get("ends_at")
        if start and end and end <= start:
            self.add_error("ends_at", "End time must be after start time.")
        product, variant, category = cleaned.get("product"), cleaned.get("variant"), cleaned.get("category")
        variants = cleaned.get("variants")
        if product and category and product.category_id != category.id and not product.category.parent_id == category.id:
            self.add_error("product", "Select a product from the selected category.")
        if variant and product and variant.product_id != product.id:
            self.add_error("variant", "Select a variant from the selected product.")
        if variants and product and any(item.product_id != product.id for item in variants):
            self.add_error("variants", "All selected variants must belong to the selected product.")
        if variants and cleaned.get("all_variants"):
            cleaned["variants"] = ProductVariant.objects.none()
        return cleaned

    def __init__(self, *args, retailer=None, admin=False, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep the numeric field compact: render 10 instead of 10.00 while
        # still allowing the model to retain decimal precision if needed.
        percentage = self.initial.get("discount_percentage")
        if percentage is not None:
            self.initial["discount_percentage"] = format(percentage, "f").rstrip("0").rstrip(".") or "0"
        self.fields["category"].queryset = Category.objects.filter(is_active=True).order_by("name")
        if retailer:
            products = Product.objects.filter(retailer=retailer, is_active=True, deleted_at__isnull=True).select_related("store")
            category_id = self.data.get(self.add_prefix("category")) or self.initial.get("category")
            if category_id:
                products = products.filter(category_id=category_id)
                self.fields["product"].queryset = products.order_by("name")
            product_id = self.data.get(self.add_prefix("product")) or self.initial.get("product")
            variant_qs = ProductVariant.objects.filter(product_id=product_id, deleted_at__isnull=True).order_by("name") if product_id else ProductVariant.objects.none()
            self.fields["variant"].queryset = variant_qs
            self.fields["variants"].queryset = variant_qs
            if self.instance and self.instance.selected_variant_ids:
                self.fields["variants"].initial = self.instance.selected_variant_ids
                self.fields["all_variants"].initial = False
        else:
            self.fields["product"].queryset = Product.objects.filter(is_active=True, deleted_at__isnull=True).select_related("store").order_by("name")
        self.fields["product"].label_from_instance = lambda item: f"{item.name} — {item.store.name}" if getattr(item, "store", None) else item.name
        if admin:
            self.fields["retailer"].required = False
            self.fields["retailer"].empty_label = "Global platform setting"
        else:
            self.fields.pop("retailer")
            self.fields.pop("message", None)
            self.fields["category"].required = False
            self.fields["category"].empty_label = "All categories (retailer default)"
            self.retailer = retailer
        self.fields["name"].label = "Sale name"
        self.fields["name"].help_text = "Internal backend label; customers see the message field instead."


class RetailerSaleCountdownSettingForm(SaleCountdownSettingForm):
    def __init__(self, *args, retailer=None, **kwargs):
        super().__init__(*args, retailer=retailer, admin=False, **kwargs)
        # The retailer UI uses the multiple variant selector. Keep the legacy
        # FK on the model for existing rules, but do not expose a second
        # single-select control in the form.
        self.fields.pop("variant", None)

    def save(self, commit=True):
        setting = super().save(commit=False)
        setting.retailer = self.retailer
        # Retailers choose scope and end time only; the sale message is
        # controlled by the admin/global rule.
        setting.message = ""
        selected_variants = self.cleaned_data.get("variants")
        if self.cleaned_data.get("all_variants"):
            setting.selected_variant_ids = []
            setting.variant = None
        else:
            selected_ids = [str(item.pk) for item in selected_variants] if selected_variants else []
            setting.selected_variant_ids = selected_ids
            # Preserve compatibility with older code by keeping the first
            # selected variant in the legacy FK as well.
            setting.variant = next(iter(selected_variants), None) if selected_variants else None
        if commit:
            setting.save()
        return setting
