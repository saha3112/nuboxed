import re
from pathlib import Path

from django.db import models

from apps.common.models import BaseModel


def _installed_fontawesome_choices():
    """Expose every free Font Awesome glyph available in the installed bundle."""
    try:
        import jazzmin
        css_path = Path(jazzmin.__file__).resolve().parent / "static/vendor/fontawesome-free/css/all.min.css"
        names = sorted(set(re.findall(r"\.fa-([a-z0-9-]+):before", css_path.read_text(encoding="utf-8"))))
        return [(f"fa-solid fa-{name}", name.replace("-", " ").title()) for name in names]
    except (ImportError, OSError):
        return []


class HomePageSettings(BaseModel):
    GOOGLE_FONT_NAMES = [
        "Inter", "Manrope", "Roboto", "Roboto Condensed", "Roboto Slab", "Open Sans",
        "Lato", "Poppins", "Montserrat", "Nunito", "Nunito Sans", "Raleway", "DM Sans",
        "Plus Jakarta Sans", "Merriweather", "Merriweather Sans", "Playfair Display", "Oswald",
        "Archivo", "Archivo Black", "Barlow", "Barlow Condensed", "Be Vietnam Pro", "Bebas Neue",
        "Bitter", "Cabin", "Cairo", "Catamaran", "Chakra Petch", "Changa", "Chivo",
        "Comfortaa", "Comic Neue", "Cormorant Garamond", "Crimson Text", "Dancing Script",
        "Dela Gothic One", "DM Mono", "DM Serif Display", "Dosis", "Droid Sans", "Eczar",
        "Epilogue", "Exo 2", "Figtree", "Fira Code", "Fira Sans", "Fira Sans Condensed",
        "Fjalla One", "Frank Ruhl Libre", "Gabarito", "Gelasio", "Gentium Book Plus", "Geologica",
        "Gloria Hallelujah", "Golos Text", "Gothic A1", "Goudy Bookletter 1911", "Great Vibes",
        "Hanken Grotesk", "Heebo", "IBM Plex Mono", "IBM Plex Sans", "IBM Plex Serif", "Inconsolata",
        "Indie Flower", "Inknut Antiqua", "Instrument Sans", "Instrument Serif", "Inter Tight",
        "Josefin Sans", "Josefin Slab", "Jost", "Kanit", "Karla", "Khand", "Klee One", "Knewave",
        "Labrada", "Lexend", "Libre Baskerville", "Libre Franklin", "Lilita One", "Lobster",
        "Lora", "Luckiest Guy", "M PLUS 1p", "M PLUS Rounded 1c", "Macondo", "Major Mono Display",
        "Marcellus", "Marck Script", "Martel", "Maven Pro", "Merriweather", "Michroma", "Mitr",
        "Mohave", "Monda", "Monoton", "Mukta", "Mulish", "Nanum Gothic", "Noto Sans",
        "Noto Sans Display", "Noto Serif", "Noto Serif Display", "Notable", "Nova Round", "Old Standard TT",
        "Onest", "Orbitron", "Outfit", "Overpass", "Overpass Mono", "Oxygen", "Pacifico",
        "Patrick Hand", "Permanent Marker", "Philosopher", "Play", "Poiret One", "Prata", "Press Start 2P",
        "Public Sans", "Quicksand", "Rajdhani", "Rakkas", "Ranchers", "Ranga", "Readex Pro", "Red Hat Display",
        "Red Hat Mono", "Red Hat Text", "REM", "Righteous", "Rokkitt", "Rubik", "Rubik Mono One",
        "Ruda", "Russo One", "Saira", "Saira Condensed", "Sarabun", "Schibsted Grotesk", "Sedan",
        "Shadows Into Light", "Signika", "Silkscreen", "Smooch Sans", "Sora", "Source Code Pro",
        "Source Sans 3", "Source Serif 4", "Space Grotesk", "Space Mono", "Special Elite", "Spectral",
        "Squada One", "Staatliches", "Starborn", "Sue Ellen Francisco", "Syne", "Teko", "Tektur",
        "Tenor Sans", "The Nautigal", "Titillium Web", "Tomorrow", "Trade Winds", "Trispace", "Ubuntu",
        "Ubuntu Mono", "Urbanist", "Varela Round", "Vazirmatn", "Victor Mono", "Vollkorn", "Voltaire",
        "Walter Turncoat", "Wix Madefor Display", "Work Sans", "Yanone Kaffeesatz", "Yellowtail", "Ysabeau",
        "Zilla Slab", "Arial", "Helvetica", "Georgia", "Times New Roman", "system-ui",
    ]
    FONT_CHOICES = [(name, name) for name in dict.fromkeys(GOOGLE_FONT_NAMES)]
    REVIEW_SOURCE_CHOICES = [("manual", "Manual review cards"), ("product", "Approved product reviews"), ("both", "Manual + approved product reviews")]
    singleton_key = models.CharField(max_length=32, unique=True, default="homepage")
    # Kept as a plain value so the admin can accept the complete, changing
    # Google Fonts catalog instead of being limited by a static choice list.
    font_family = models.CharField(max_length=80, default="Inter")
    heading_color = models.CharField(max_length=9, default="#111827")
    body_color = models.CharField(max_length=9, default="#667085")
    accent_color = models.CharField(max_length=9, default="#5b4df7")
    trust_title_color = models.CharField(max_length=9, default="#111827")
    trust_text_color = models.CharField(max_length=9, default="#667085")
    trust_icon_color = models.CharField(max_length=9, default="#5b4df7")
    trust_font_family = models.CharField(max_length=80, default="Inter")
    trust_title_font_size = models.PositiveIntegerField(default=14)
    trust_text_font_size = models.PositiveIntegerField(default=12)
    trust_icon_size = models.PositiveIntegerField(default=19)
    trending_font_family = models.CharField(max_length=80, default="Inter")
    trending_title_color = models.CharField(max_length=9, default="#111827")
    trending_text_color = models.CharField(max_length=9, default="#667085")
    trending_price_color = models.CharField(max_length=9, default="#111827")
    trending_title_font_size = models.PositiveIntegerField(default=14)
    trending_meta_font_size = models.PositiveIntegerField(default=12)
    trending_price_font_size = models.PositiveIntegerField(default=18)
    trending_heading_font_size = models.PositiveIntegerField(default=42)
    trending_subtitle_font_size = models.PositiveIntegerField(default=16)
    category_title = models.CharField(max_length=120, default="Shop by category")
    category_subtitle = models.CharField(max_length=255, default="Everything you need, beautifully curated.")
    category_card_count = models.PositiveIntegerField(default=4)
    CATEGORY_IMAGE_FIT_CHOICES = [("contain", "Show full image (no crop)"), ("cover", "Fill card (may crop edges)")]
    category_image_fit = models.CharField(max_length=12, choices=CATEGORY_IMAGE_FIT_CHOICES, default="contain")
    trending_title = models.CharField(max_length=120, default="Trending now")
    trending_subtitle = models.CharField(max_length=255, default="Popular picks our customers are loving.")
    trending_product_count = models.PositiveIntegerField(default=8)
    trending_view_all_label = models.CharField(max_length=100, default="View all products →")
    trending_view_all_url = models.CharField(max_length=255, default="/products/")
    show_product_badge = models.BooleanField(default=True)
    show_product_wishlist = models.BooleanField(default=True)
    show_product_rating = models.BooleanField(default=True)
    show_product_price = models.BooleanField(default=True)
    show_product_add_button = models.BooleanField(default=True)
    reviews_title = models.CharField(max_length=120, default="Loved by our customers")
    reviews_subtitle = models.CharField(max_length=255, default="Real feedback from the Nuboxed community.")
    review_card_count = models.PositiveIntegerField(default=3)
    review_source = models.CharField(max_length=20, choices=REVIEW_SOURCE_CHOICES, default="manual")
    reviews_font_family = models.CharField(max_length=80, default="Inter")
    reviews_quote_color = models.CharField(max_length=9, default="#475467")
    reviews_name_color = models.CharField(max_length=9, default="#111827")
    reviews_role_color = models.CharField(max_length=9, default="#667085")
    reviews_quote_font_size = models.PositiveIntegerField(default=15)
    reviews_name_font_size = models.PositiveIntegerField(default=14)
    reviews_role_font_size = models.PositiveIntegerField(default=12)
    reviews_heading_font_size = models.PositiveIntegerField(default=42)
    reviews_subtitle_font_size = models.PositiveIntegerField(default=16)

    def __str__(self):
        return "Homepage settings"


class HomeTrustCard(BaseModel):
    ICON_MODE_CHOICES = [("text", "Text / Emoji"), ("fontawesome", "Font Awesome"), ("svg", "Custom SVG")]
    FONTAWESOME_CHOICES = [
        ("fa-solid fa-truck-fast", "Truck / Shipping"), ("fa-solid fa-rotate-left", "Returns"),
        ("fa-solid fa-lock", "Secure payment"), ("fa-solid fa-headset", "Support"),
        ("fa-solid fa-shield-halved", "Security"), ("fa-solid fa-box", "Package"),
        ("fa-solid fa-star", "Star"), ("fa-solid fa-heart", "Heart"),
        ("fa-solid fa-circle-check", "Verified"), ("fa-solid fa-comments", "Messages"),
        ("fa-solid fa-house", "Home"), ("fa-solid fa-user", "User"), ("fa-solid fa-users", "Customers"),
        ("fa-solid fa-cart-shopping", "Cart"), ("fa-solid fa-bag-shopping", "Shopping bag"),
        ("fa-solid fa-gift", "Gift"), ("fa-solid fa-tag", "Tag"), ("fa-solid fa-tags", "Tags"),
        ("fa-solid fa-bolt", "Fast / Offers"), ("fa-solid fa-fire", "Popular"),
        ("fa-solid fa-check", "Check"), ("fa-solid fa-circle-info", "Information"),
        ("fa-solid fa-circle-question", "Help"), ("fa-solid fa-envelope", "Email"),
        ("fa-solid fa-phone", "Phone"), ("fa-solid fa-location-dot", "Location"),
        ("fa-solid fa-truck", "Delivery truck"), ("fa-solid fa-box-open", "Open box"),
        ("fa-solid fa-credit-card", "Card payment"), ("fa-solid fa-wallet", "Wallet"),
        ("fa-solid fa-percent", "Discount"), ("fa-solid fa-thumbs-up", "Like"),
        ("fa-solid fa-clock", "Time"), ("fa-solid fa-globe", "Global"),
        ("fa-solid fa-magnifying-glass", "Search"), ("fa-solid fa-arrow-right", "Arrow right"),
        ("fa-solid fa-arrow-left", "Arrow left"), ("fa-solid fa-arrow-up", "Arrow up"),
        ("fa-solid fa-arrow-down", "Arrow down"), ("fa-solid fa-check-double", "Double check"),
        ("fa-solid fa-xmark", "Close"), ("fa-solid fa-plus", "Add"), ("fa-solid fa-minus", "Remove"),
        ("fa-solid fa-bars", "Menu"), ("fa-solid fa-gear", "Settings"), ("fa-solid fa-sliders", "Filters"),
        ("fa-solid fa-download", "Download"), ("fa-solid fa-upload", "Upload"), ("fa-solid fa-share-nodes", "Share"),
        ("fa-solid fa-link", "Link"), ("fa-solid fa-image", "Image"), ("fa-solid fa-camera", "Camera"),
        ("fa-solid fa-video", "Video"), ("fa-solid fa-music", "Music"), ("fa-solid fa-bookmark", "Bookmark"),
        ("fa-solid fa-bell", "Notifications"), ("fa-solid fa-calendar", "Calendar"), ("fa-solid fa-calendar-check", "Confirmed date"),
        ("fa-solid fa-location-crosshairs", "Current location"), ("fa-solid fa-map", "Map"), ("fa-solid fa-store", "Store"),
        ("fa-solid fa-shop", "Shop"), ("fa-solid fa-building", "Building"), ("fa-solid fa-warehouse", "Warehouse"),
        ("fa-solid fa-truck-ramp-box", "Dispatch"), ("fa-solid fa-receipt", "Receipt"), ("fa-solid fa-file-invoice", "Invoice"),
        ("fa-solid fa-money-bill", "Cash"), ("fa-solid fa-coins", "Coins"), ("fa-solid fa-chart-line", "Growth"),
        ("fa-solid fa-circle-up", "Up"), ("fa-solid fa-circle-down", "Down"), ("fa-solid fa-lightbulb", "Idea"),
        ("fa-solid fa-sparkles", "Featured"), ("fa-solid fa-crown", "Premium"), ("fa-solid fa-medal", "Award"),
        ("fa-solid fa-leaf", "Eco"), ("fa-solid fa-recycle", "Sustainable"), ("fa-solid fa-wand-magic-sparkles", "Magic"),
        ("fa-regular fa-heart", "Light heart"), ("fa-regular fa-star", "Light star"),
        ("fa-regular fa-circle-check", "Light verified"), ("fa-regular fa-circle-user", "Light user"),
        ("fa-regular fa-clock", "Light time"), ("fa-regular fa-calendar", "Light calendar"),
        ("fa-regular fa-envelope", "Light email"), ("fa-regular fa-bell", "Light notification"),
        ("fa-regular fa-bookmark", "Light bookmark"), ("fa-regular fa-image", "Light image"),
        ("fa-regular fa-face-smile", "Smile"), ("fa-regular fa-face-laugh", "Happy"),
        ("fa-regular fa-comment", "Light comment"), ("fa-regular fa-comments", "Light messages"),
        ("fa-regular fa-thumbs-up", "Light like"), ("fa-regular fa-circle-question", "Light help"),
        ("fa-brands fa-facebook", "Facebook"), ("fa-brands fa-instagram", "Instagram"),
        ("fa-brands fa-x-twitter", "X / Twitter"), ("fa-brands fa-youtube", "YouTube"),
        ("fa-brands fa-whatsapp", "WhatsApp"), ("fa-brands fa-linkedin", "LinkedIn"),
        ("fa-brands fa-tiktok", "TikTok"), ("fa-brands fa-telegram", "Telegram"),
        ("fa-brands fa-google", "Google"), ("fa-brands fa-apple", "Apple"),
        ("fa-brands fa-amazon", "Amazon"), ("fa-brands fa-shopify", "Shopify"),
        ("fa-solid fa-circle", "Circle"), ("fa-solid fa-square", "Square"),
        ("fa-solid fa-diamond", "Diamond"), ("fa-solid fa-location-pin", "Pin"),
        ("fa-solid fa-paper-plane", "Send"), ("fa-solid fa-print", "Print"),
        ("fa-solid fa-filter", "Filter"), ("fa-solid fa-list", "List"),
        ("fa-solid fa-table-cells", "Grid"), ("fa-solid fa-grip", "Arrange"),
        ("fa-solid fa-ellipsis", "More"), ("fa-solid fa-ellipsis-vertical", "More vertical"),
        ("fa-solid fa-eye", "View"), ("fa-solid fa-eye-slash", "Hidden"),
        ("fa-solid fa-pen", "Edit"), ("fa-solid fa-trash", "Delete"),
        ("fa-solid fa-rotate", "Refresh"), ("fa-solid fa-power-off", "Power"),
    ] + _installed_fontawesome_choices()
    settings = models.ForeignKey(HomePageSettings, related_name="trust_cards", on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    text = models.CharField(max_length=160)
    icon_mode = models.CharField(max_length=20, choices=ICON_MODE_CHOICES, default="text")
    icon = models.CharField(max_length=20, default="✓")
    fontawesome_icon = models.CharField(max_length=60, choices=FONTAWESOME_CHOICES, default="fa-solid fa-circle-check")
    custom_svg = models.TextField(blank=True, help_text="Paste a safe inline SVG, or upload an SVG file below.")
    icon_svg_file = models.FileField(upload_to="homepage/icons/", blank=True)
    icon_color = models.CharField(max_length=9, default="#5b4df7")
    title_color = models.CharField(max_length=9, default="#111827")
    text_color = models.CharField(max_length=9, default="#667085")
    use_manual_style = models.BooleanField(default=False, help_text="Override the global trust-card typography and colors for this card.")
    title_font_size = models.PositiveIntegerField(default=14)
    text_font_size = models.PositiveIntegerField(default=12)
    icon_size = models.PositiveIntegerField(default=19)
    font_family = models.CharField(max_length=80, default="Inter")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "created_at")


class HomeReviewCard(BaseModel):
    settings = models.ForeignKey(HomePageSettings, related_name="review_cards", on_delete=models.CASCADE)
    quote = models.TextField()
    reviewer_name = models.CharField(max_length=100)
    role = models.CharField(max_length=100, default="Verified shopper")
    rating = models.PositiveIntegerField(default=5)
    avatar_color = models.CharField(max_length=9, default="#e9d5ff")
    text_color = models.CharField(max_length=9, default="#475467")
    font_family = models.CharField(max_length=80, default="Inter")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "created_at")


class Page(BaseModel):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    content = models.TextField(blank=True)
    is_published = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.title


class DynamicForm(BaseModel):
    BUTTON_ALIGNMENT_CHOICES = [("left", "Left"), ("center", "Center"), ("right", "Right")]

    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    description = models.TextField(blank=True)
    submit_button_text = models.CharField(max_length=80, default="Submit")
    submit_button_alignment = models.CharField(max_length=10, choices=BUTTON_ALIGNMENT_CHOICES, default="left")
    success_message = models.CharField(max_length=255, default="Thanks! Your response has been submitted.")
    error_message = models.CharField(max_length=255, default="Please correct the highlighted fields and try again.")
    show_heading = models.BooleanField(default=True)
    captcha_enabled = models.BooleanField(default=False, help_text="Show the configured captcha on this public form.")
    field_gap = models.PositiveIntegerField(default=18, help_text="Vertical spacing between form fields in pixels.")
    is_published = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.name


class DynamicFormField(BaseModel):
    FIELD_TYPES = [("text", "Short text"), ("textarea", "Long text"), ("email", "Email"), ("phone", "Phone"), ("number", "Number"), ("date", "Date"), ("select", "Dropdown"), ("radio", "Radio choices"), ("checkbox", "Checkboxes"), ("file", "File upload"), ("hidden", "Hidden")]
    ALIGNMENT_CHOICES = [("left", "Left"), ("center", "Center"), ("right", "Right")]
    form = models.ForeignKey(DynamicForm, related_name="fields", on_delete=models.CASCADE)
    label = models.CharField(max_length=160)
    key = models.SlugField(max_length=100)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES, default="text")
    placeholder = models.CharField(max_length=255, blank=True)
    help_text = models.CharField(max_length=255, blank=True)
    options = models.JSONField(default=list, blank=True)
    default_value = models.CharField(max_length=255, blank=True)
    required = models.BooleanField(default=False)
    show_label = models.BooleanField(default=True)
    alignment = models.CharField(max_length=10, choices=ALIGNMENT_CHOICES, default="left")
    date_minimum = models.CharField(max_length=10, blank=True, default="")
    date_maximum = models.CharField(max_length=10, blank=True, default="")
    date_block_weekends = models.BooleanField(default=False)
    date_specific_dates = models.JSONField(default=list, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("sort_order", "created_at")
        constraints = [models.UniqueConstraint(fields=("form", "key"), name="unique_dynamic_form_field_key")]

    def __str__(self):
        return f"{self.form.name}: {self.label}"


class DynamicFormSubmission(BaseModel):
    form = models.ForeignKey(DynamicForm, related_name="submissions", on_delete=models.CASCADE)
    data = models.JSONField(default=dict, blank=True)
    submitted_by = models.ForeignKey("users.User", null=True, blank=True, on_delete=models.SET_NULL)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.form.name} · {self.created_at:%d %b %Y %H:%M}"


class Slider(BaseModel):
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=255, blank=True)
    eyebrow = models.CharField(max_length=100, default="Nuboxed marketplace", blank=True)
    cta_label = models.CharField(max_length=80, blank=True)
    cta_url = models.CharField(max_length=255, blank=True)
    secondary_cta_label = models.CharField(max_length=80, default="Explore categories", blank=True)
    secondary_cta_url = models.CharField(max_length=255, default="#n8-categories", blank=True)
    image = models.ImageField(upload_to="sliders/", blank=True)
    right_image = models.ImageField(
        upload_to="sliders/right/", blank=True,
        help_text="Optional right-side image override. This takes priority over the selected product image.",
    )
    product_link_label = models.CharField(max_length=80, default="View product", blank=True)
    product_link_url = models.CharField(
        max_length=255, blank=True,
        help_text="Optional manual URL. If blank, the selected product detail page is used automatically.",
    )
    meta_primary_title = models.CharField(max_length=80, default="Verified", blank=True)
    meta_primary_text = models.CharField(max_length=100, default="product data", blank=True)
    meta_secondary_title = models.CharField(max_length=80, default="Secure", blank=True)
    meta_secondary_text = models.CharField(max_length=100, default="checkout", blank=True)
    retailer = models.ForeignKey(
        "retailers.Retailer", null=True, blank=True,
        related_name="homepage_sliders", on_delete=models.SET_NULL,
        help_text="Optional retailer whose product is shown on the right side.",
    )
    product = models.ForeignKey(
        "catalog.Product", null=True, blank=True,
        related_name="homepage_sliders", on_delete=models.SET_NULL,
        help_text="Optional approved product to show on the right side of this slide.",
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    sort_order = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return self.title


class FeaturedBanner(BaseModel):
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=255, blank=True)
    link_url = models.CharField(max_length=255, blank=True)
    image = models.ImageField(upload_to="featured-banners/", blank=True)
    status = models.CharField(max_length=32, default="draft")
    placement = models.CharField(max_length=64, default="homepage")

    def __str__(self) -> str:
        return self.title
