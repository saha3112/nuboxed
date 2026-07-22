from django import forms
from django.contrib import admin

from apps.catalog.models import Product
from apps.retailers.models import Retailer
from .models import FeaturedBanner, Page, Slider

admin.site.register(Page)
class SliderAdminForm(forms.ModelForm):
    class Meta:
        model = Slider
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        destination_choices = [
            ("", "Select a destination"), ("/", "Homepage"), ("/products/", "Products"),
            ("#n8-categories", "Shop by category section"), ("/stores/", "Stores"),
            ("/contact/", "Contact"), ("/cart/", "Cart"), ("/checkout/", "Checkout"),
            ("/wishlist/", "Wishlist"), ("/compare/", "Compare"), ("/account/orders/", "Customer orders"),
        ]
        destination_choices.extend(
            (f"/pages/{page.slug}/", f"Page: {page.title}")
            for page in Page.objects.filter(is_active=True, is_published=True).order_by("title")
        )
        self.fields["cta_url"].widget = forms.HiddenInput()
        self.fields["secondary_cta_url"].widget = forms.HiddenInput()
        self.fields["image"].widget = forms.HiddenInput()
        self.fields["cta_target"] = forms.ChoiceField(label="First button destination", choices=destination_choices + [("__manual__", "Manual URL")], required=False, help_text="Choose a built-in/CMS page or select Manual URL below.")
        self.fields["cta_manual_url"] = forms.CharField(label="First button manual URL", required=False, widget=forms.URLInput(attrs={"placeholder": "https://example.com/page or /custom-page/"}), help_text="Used only when First button destination is Manual URL.")
        self.fields["product_link_label"].label = "Right product button label"
        self.fields["product_link_url"].label = "Right product manual URL"
        self.fields["secondary_cta_target"] = forms.ChoiceField(
            label="Second button destination", choices=destination_choices + [("__manual__", "Manual URL")],
            required=False, help_text="Choose a built-in/CMS page or select Manual URL below.",
        )
        self.fields["secondary_cta_manual_url"] = forms.CharField(
            label="Manual URL", required=False,
            widget=forms.URLInput(attrs={"placeholder": "https://example.com/page or /custom-page/"}),
            help_text="Used only when Second button destination is Manual URL.",
        )
        cta_fields = {"cta_target", "cta_manual_url", "secondary_cta_label", "secondary_cta_target", "secondary_cta_manual_url", "product_link_label", "product_link_url"}
        remaining = [name for name in self.fields if name not in cta_fields]
        insert_at = remaining.index("cta_label") + 1 if "cta_label" in remaining else len(remaining)
        self.order_fields(remaining[:insert_at] + ["cta_target", "cta_manual_url", "secondary_cta_label", "secondary_cta_target", "secondary_cta_manual_url", "product_link_label", "product_link_url"] + remaining[insert_at:])
        current_primary_url = getattr(self.instance, "cta_url", "") or ""
        if current_primary_url in {value for value, _ in destination_choices}:
            self.initial["cta_target"] = current_primary_url
        else:
            self.initial["cta_target"] = "__manual__" if current_primary_url else ""
            self.initial["cta_manual_url"] = current_primary_url
        current_url = getattr(self.instance, "secondary_cta_url", "") or ""
        known_urls = {value for value, _ in destination_choices}
        if current_url in known_urls:
            self.initial["secondary_cta_target"] = current_url
        else:
            self.initial["secondary_cta_target"] = "__manual__" if current_url else ""
            self.initial["secondary_cta_manual_url"] = current_url
        self.fields["eyebrow"].label = "Eyebrow / small heading"
        self.fields["meta_primary_title"].label = "Trust point 1 title"
        self.fields["meta_primary_text"].label = "Trust point 1 text"
        self.fields["meta_secondary_title"].label = "Trust point 2 title"
        self.fields["meta_secondary_text"].label = "Trust point 2 text"
        self.fields["right_image"].label = "Right-side image override"
        self.fields["retailer"].queryset = Retailer.objects.filter(
            is_active=True, status=Retailer.STATUS_APPROVED
        ).order_by("display_name", "legal_name")
        product_qs = Product.objects.filter(
            is_active=True, status=Product.STATUS_APPROVED
        ).select_related("retailer").order_by("name")
        retailer_id = self.data.get("retailer") or getattr(self.instance, "retailer_id", None)
        if retailer_id:
            product_qs = product_qs.filter(retailer_id=retailer_id)
        else:
            product_qs = product_qs.none()
        self.fields["product"].queryset = product_qs

    def clean(self):
        cleaned = super().clean()
        primary_destination = cleaned.get("cta_target")
        primary_manual_url = (cleaned.get("cta_manual_url") or "").strip()
        cleaned["cta_url"] = primary_manual_url if primary_destination == "__manual__" else (primary_destination or "")
        destination = cleaned.get("secondary_cta_target")
        manual_url = (cleaned.get("secondary_cta_manual_url") or "").strip()
        cleaned["secondary_cta_url"] = manual_url if destination == "__manual__" else (destination or "")
        retailer = cleaned.get("retailer")
        product = cleaned.get("product")
        if product and retailer and product.retailer_id != retailer.id:
            self.add_error("product", "Select a product belonging to the selected retailer.")
        if product and not retailer:
            cleaned["retailer"] = product.retailer
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.cta_url = self.cleaned_data.get("cta_url", "")
        instance.secondary_cta_url = self.cleaned_data.get("secondary_cta_url", "")
        if commit:
            instance.save()
            self.save_m2m()
        return instance


@admin.register(Slider)
class SliderAdmin(admin.ModelAdmin):
    form = SliderAdminForm
    list_display = ("title", "retailer_name", "product_name", "status", "sort_order", "is_active")
    list_filter = ("status", "is_active", "retailer")
    search_fields = ("title", "subtitle", "retailer__legal_name", "retailer__display_name", "product__name", "product__sku")
    ordering = ("sort_order", "-created_at")
    fieldsets = (
        ("Slide content", {"fields": ("eyebrow", "title", "subtitle", "cta_label", "cta_target", "cta_manual_url", "secondary_cta_label", "secondary_cta_target", "secondary_cta_manual_url", "status", "sort_order", "is_active")}),
        (
            "Trust points",
            {"fields": ("meta_primary_title", "meta_primary_text", "meta_secondary_title", "meta_secondary_text")},
        ),
        (
            "Retailer product spotlight",
            {
                "description": "Choose a retailer and approved product. The product's first image appears on the right. An uploaded right-side image overrides the product image.",
                "fields": ("retailer", "product", "right_image", "product_link_label", "product_link_url"),
            },
        ),
    )

    @admin.display(description="Retailer")
    def retailer_name(self, obj):
        return obj.retailer.display_name or obj.retailer.legal_name if obj.retailer else "—"

    @admin.display(description="Product")
    def product_name(self, obj):
        return obj.product.name if obj.product else "—"
admin.site.register(FeaturedBanner)
