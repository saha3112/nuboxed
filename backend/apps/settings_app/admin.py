from django.contrib import admin

from .models import BrandSettings, MenuItem, PageText, Setting, SiteLogo, SocialLink, MegaMenuSettings, StorefrontLocationMessages, SaleCountdownSetting


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = ("key", "is_active", "updated_at")
    search_fields = ("key",)
    list_filter = ("is_active",)


@admin.register(SaleCountdownSetting)
class SaleCountdownSettingAdmin(admin.ModelAdmin):
    list_display = ("__str__", "message", "ends_at", "is_active", "updated_at")
    list_filter = ("is_active", "retailer", "category")
    search_fields = ("message", "retailer__display_name", "category__name")


@admin.register(BrandSettings)
class BrandSettingsAdmin(admin.ModelAdmin):
    list_display = ("brand_name", "brand_tagline", "is_active", "updated_at")
    search_fields = ("brand_name", "brand_tagline")
    list_filter = ("is_active",)


@admin.register(SiteLogo)
class SiteLogoAdmin(admin.ModelAdmin):
    list_display = ("alt_text", "logo_image", "is_active", "updated_at")
    search_fields = ("alt_text",)
    list_filter = ("is_active",)


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("title", "parent", "url", "sort_order", "is_active", "updated_at")
    search_fields = ("title", "url")
    list_filter = ("is_active",)
    ordering = ("sort_order", "title")


@admin.register(PageText)
class PageTextAdmin(admin.ModelAdmin):
    list_display = ("key", "title", "breadcrumb_label", "menu_label", "is_active", "updated_at")
    search_fields = ("key", "title", "breadcrumb_label", "menu_label")
    list_filter = ("is_active",)
    ordering = ("key",)


@admin.register(StorefrontLocationMessages)
class StorefrontLocationMessagesAdmin(admin.ModelAdmin):
    list_display = ("__str__", "is_active", "updated_at")
    list_filter = ("is_active",)
    fieldsets = (
        ("Stores page (/stores/)", {
            "description": "These texts are shown on the public Stores page when nearby-store filtering is active.",
            "fields": ("no_stores_message", "other_location_message", "is_active"),
        }),
    )



@admin.register(MegaMenuSettings)
class MegaMenuSettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "font_family", "background_color", "text_color", "updated_at")
    fieldsets = (
        ("Typography", {
            "fields": ("font_family", "font_size_menu", "font_size_heading")
        }),
        ("Colors", {
            "fields": ("background_color", "text_color", "hover_color", "heading_color")
        }),
        ("Store Promo Block", {
            "fields": ("promo_subtitle", "promo_title", "promo_description", "promo_button_text")
        }),
    )
