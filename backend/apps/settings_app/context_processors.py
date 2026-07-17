from apps.settings_app.models import BrandSettings, MenuItem, PageText, SiteLogo, SocialLink, MegaMenuSettings, StorefrontLocationMessages

def global_brand_settings(request):
    settings = BrandSettings.objects.filter(is_active=True).first()
    site_logo = SiteLogo.objects.filter(is_active=True).order_by("-updated_at").first()
    return {
        "global_brand_settings": settings,
        "global_site_logo": site_logo,
        "global_menu_items": MenuItem.objects.filter(is_active=True, parent__isnull=True).prefetch_related("children").order_by("sort_order", "title"),
        "storefront_page_texts": {page.key: page for page in PageText.objects.filter(is_active=True)},
        "storefront_location_messages": StorefrontLocationMessages.objects.filter(is_active=True).first(),
        "global_social_links": SocialLink.objects.filter(is_active=True).order_by("sort_order", "platform"),
        "global_mega_menu_settings": MegaMenuSettings.objects.first(),
    }
