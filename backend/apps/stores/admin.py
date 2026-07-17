from django.contrib import admin

from .models import Store, StoreRating


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "contact_email", "country_code", "status", "is_active")
    search_fields = ("name", "slug", "contact_email")
    list_filter = ("status", "country_code", "is_active")
    exclude = ("icon",)

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
