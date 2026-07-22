from django.db import models

from apps.common.models import BaseModel
from apps.catalog.models import Category
from apps.retailers.models import Retailer


class Setting(BaseModel):
    key = models.CharField(max_length=120, unique=True)
    value = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return self.key


class SaleCountdownSetting(BaseModel):
    """Global or category-level countdown defaults.

    A null retailer is the platform default. A retailer value makes the
    setting private to that retailer; adding a category makes it a category
    override. Product-specific values remain on Product for fine-grained
    control.
    """

    retailer = models.ForeignKey(Retailer, null=True, blank=True, on_delete=models.CASCADE, related_name="sale_countdown_settings")
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.CASCADE, related_name="sale_countdown_settings")
    message = models.CharField(max_length=160, default="Hurry up! Sale ends in:")
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Sale Countdown Setting"
        verbose_name_plural = "Sale Countdown Settings"
        ordering = ("retailer_id", "category_id", "-updated_at")

    def __str__(self):
        owner = self.retailer.display_name if self.retailer_id else "Global"
        scope = self.category.name if self.category_id else "All categories"
        return f"{owner} — {scope}"


class BrandSettings(BaseModel):
    logo_big = models.ImageField(upload_to="logos/", blank=True, null=True, help_text="Large logo shown when sidebar is expanded.")
    logo_small = models.ImageField(upload_to="logos/", blank=True, null=True, help_text="Small icon logo shown when sidebar is collapsed.")
    notification_empty_image = models.ImageField(
        upload_to="logos/",
        blank=True,
        null=True,
        help_text="Custom image displayed when there are no notifications."
    )
    brand_name = models.CharField(max_length=100, default="Nuboxed")
    brand_tagline = models.CharField(max_length=100, default="Super Admin", blank=True)
    footer_description = models.CharField(max_length=255, default="Curated electronics, verified retailers, transparent delivery, and smarter product discovery.", blank=True)
    footer_top_title = models.CharField(max_length=180, default="Good products. Better prices. A simpler way to shop.")
    footer_top_subtitle = models.CharField(max_length=255, default="Get product launches, members-only offers and shopping updates delivered to your inbox.")
    footer_explore_title = models.CharField(max_length=100, default="Explore")
    footer_support_title = models.CharField(max_length=100, default="Support")
    footer_font_family = models.CharField(max_length=80, default="Inter")
    footer_heading_color = models.CharField(max_length=9, default="#ffffff")
    footer_text_color = models.CharField(max_length=9, default="#b8b8b8")
    footer_link_color = models.CharField(max_length=9, default="#ffffff")
    footer_heading_font_size = models.PositiveIntegerField(default=16)
    footer_text_font_size = models.PositiveIntegerField(default=14)
    footer_link_font_size = models.PositiveIntegerField(default=14)
    footer_link_decoration = models.CharField(max_length=12, choices=[("none", "No underline"), ("hover", "Underline on hover"), ("always", "Always underline")], default="none")
    footer_show_icons = models.BooleanField(default=True)
    location_prompt_enabled = models.BooleanField(
        default=True,
        help_text="Show the one-time storefront location permission prompt to visitors.",
    )

    class Meta:
        verbose_name = "Brand Settings"
        verbose_name_plural = "Brand Settings"

    def __str__(self) -> str:
        return self.brand_name


class SiteLogo(BaseModel):
    logo_image = models.ImageField(upload_to="logos/", help_text="Upload your website logo.")
    alt_text = models.CharField(max_length=255, default="Nuboxed", blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"Logo: {self.alt_text} ({'Active' if self.is_active else 'Inactive'})"


class MenuItem(BaseModel):
    title = models.CharField(max_length=100)
    url = models.CharField(max_length=255, help_text="e.g. /products/ or https://google.com")
    parent = models.ForeignKey("self", null=True, blank=True, related_name="children", on_delete=models.CASCADE)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.title} -> {self.url}"


class PageText(BaseModel):
    key = models.SlugField(max_length=80, unique=True, help_text="Stable key used by storefront templates, e.g. stores")
    title = models.CharField(max_length=160)
    breadcrumb_label = models.CharField(max_length=160, blank=True)
    menu_label = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Storefront Page Text"
        verbose_name_plural = "Storefront Page Texts"
        ordering = ("key",)

    def __str__(self) -> str:
        return self.title


class StorefrontLocationMessages(BaseModel):
    """Editable fallback copy shown when location filtering finds no nearby stores."""

    no_stores_message = models.CharField(
        max_length=255,
        default="No more stores found in your current location.",
        verbose_name="Stores page — no nearby stores message",
        help_text="Message shown above the alternate-location button on the Stores page.",
    )
    other_location_message = models.CharField(
        max_length=255,
        default="Do you want to see stores from stores in another location?",
        verbose_name="Stores page — other location button text",
        help_text="Button text that lets visitors view stores from another location.",
    )

    class Meta:
        verbose_name = "Stores Page Text Settings"
        verbose_name_plural = "Stores Page Text Settings"

    def __str__(self) -> str:
        return "Stores page (/stores/) text settings"


class SocialLink(BaseModel):
    platform = models.CharField(max_length=50, help_text="e.g. Facebook, X, Instagram, LinkedIn")
    url = models.URLField(help_text="URL of the social handle profile")
    icon_class = models.CharField(max_length=100, help_text="FontAwesome icon class, e.g. fa-brands fa-facebook-f")
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.platform}: {self.url}"


GOOGLE_FONTS_CHOICES = (
    ("Inter", "Inter"),
    ("Roboto", "Roboto"),
    ("Open Sans", "Open Sans"),
    ("Lato", "Lato"),
    ("Montserrat", "Montserrat"),
    ("Poppins", "Poppins"),
    ("Noto Sans", "Noto Sans"),
    ("Oswald", "Oswald"),
    ("Raleway", "Raleway"),
    ("Ubuntu", "Ubuntu"),
    ("Nunito", "Nunito"),
    ("Playfair Display", "Playfair Display"),
    ("Rubik", "Rubik"),
    ("Merriweather", "Merriweather"),
    ("PT Sans", "PT Sans"),
    ("Work Sans", "Work Sans"),
    ("Fira Sans", "Fira Sans"),
    ("Quicksand", "Quicksand"),
    ("Barlow", "Barlow"),
    ("Mulish", "Mulish"),
)

class MegaMenuSettings(BaseModel):
    font_family = models.CharField(max_length=100, choices=GOOGLE_FONTS_CHOICES, default="Inter", help_text="Choose a Google Font")
    font_size_menu = models.IntegerField(default=14, help_text="Font size in px for menu items")
    font_size_heading = models.IntegerField(default=15, help_text="Font size in px for column headings")
    
    background_color = models.CharField(max_length=20, default="#ffffff", help_text="Menu background color HEX")
    text_color = models.CharField(max_length=20, default="#444444", help_text="Menu item text color HEX")
    hover_color = models.CharField(max_length=20, default="#0b55e5", help_text="Menu item hover color HEX")
    heading_color = models.CharField(max_length=20, default="#222222", help_text="Menu heading color HEX")

    promo_subtitle = models.CharField(max_length=100, default="SPECIAL OFFER", help_text="Store mega menu promo subtitle")
    promo_title = models.CharField(max_length=100, default="Visit Our Stores", help_text="Store mega menu promo title")
    promo_description = models.TextField(default="Find the best deals at a store near you.", help_text="Promo description")
    promo_button_text = models.CharField(max_length=50, default="VIEW ALL", help_text="Promo button text")

    class Meta:
        verbose_name = "Mega Menu Settings"
        verbose_name_plural = "Mega Menu Settings"

    def __str__(self) -> str:
        return "Global Mega Menu Configuration"
