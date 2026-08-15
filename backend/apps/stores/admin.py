from django.contrib import admin
from django import forms
from django.utils.text import slugify

from .models import Store, StoreRating


class StoreAdminForm(forms.ModelForm):
    slug = forms.SlugField(
        required=False,
        help_text="Leave blank to generate this URL from the store name, or enter a custom URL slug.",
    )

    class Meta:
        model = Store
        fields = "__all__"


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    form = StoreAdminForm
    list_display = ("name", "slug", "contact_email", "country_code", "status", "is_active")
    search_fields = ("name", "slug", "contact_email")
    list_filter = ("status", "country_code", "is_active")
    exclude = ("icon",)
    prepopulated_fields = {"slug": ("name",)}

    def save_model(self, request, obj, form, change):
        if not (obj.slug or "").strip():
            base_slug = slugify(obj.name) or "store"
            candidate = base_slug
            counter = 2
            while Store.objects.filter(slug=candidate).exclude(pk=obj.pk).exists():
                candidate = f"{base_slug}-{counter}"
                counter += 1
            obj.slug = candidate
        super().save_model(request, obj, form, change)

    fieldsets = (
        ("Basic Identity", {
            "fields": (
                "retailer",
                "name",
                "slug",
                "description",
                "status",
                "is_active",
            )
        }),
        ("Visuals", {
            "fields": ("logo", "banner"),
        }),
        ("Store Page Builder", {
            "fields": (
                "store_page_tagline",
                "store_page_announcement",
                "store_page_sections",
            ),
            "description": "Amazon-style store page modules. Sections are stored as JSON and can also be edited from the retailer store form.",
        }),
        ("Contact & Location", {
            "fields": (
                "contact_email",
                "contact_phone",
                "contact_whatsapp",
                "address_line1",
                "address_line2",
                "city",
                "state",
                "postal_code",
                "country_code",
            )
        }),
        ("Commerce & Settings", {
            "fields": (
                "currency_code",
                "rating",
                "average_delivery_days",
            )
        }),
        ("Social Presence", {
            "fields": (
                "website_url",
                "facebook_url",
                "instagram_url",
                "linkedin_url",
                "x_url",
                "youtube_url",
            ),
            "classes": ("collapse",)
        }),
    )


@admin.register(StoreRating)
class StoreRatingAdmin(admin.ModelAdmin):
    list_display = ("store", "reviewer_name", "rating", "is_approved", "created_at")
    list_filter = ("is_approved", "rating", "created_at")
    search_fields = ("store__name", "reviewer_name", "comment")
    autocomplete_fields = ("store",)
