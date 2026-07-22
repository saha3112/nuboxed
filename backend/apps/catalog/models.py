from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.conf import settings

from apps.common.models import BaseModel


class Category(BaseModel):
    description = models.TextField(blank=True)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    is_featured = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=models.CASCADE,
    )
    seo_title = models.CharField(max_length=255, blank=True)
    seo_description = models.CharField(max_length=320, blank=True)
    category_image_desktop = models.ImageField(
        upload_to="categories/desktop/", blank=True,
        help_text="Homepage category card image for desktop screens.",
    )
    category_image_tablet = models.ImageField(
        upload_to="categories/tablet/", blank=True,
        help_text="Optional homepage category card image for tablet screens.",
    )
    category_image_mobile = models.ImageField(
        upload_to="categories/mobile/", blank=True,
        help_text="Optional homepage category card image for mobile screens.",
    )
    category_image_alt = models.CharField(
        max_length=255, blank=True,
        help_text="Accessible alt text for the homepage category image.",
    )

    @property
    def children_with_products(self):
        return self.children.filter(is_active=True, products__isnull=False).distinct().order_by("sort_order", "name")

    def __str__(self) -> str:
        return self.name


class Brand(BaseModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    logo = models.ImageField(upload_to="brands/", blank=True)
    description = models.TextField(blank=True)
    website_url = models.URLField(blank=True)
    seo_title = models.CharField(max_length=255, blank=True)
    seo_description = models.CharField(max_length=320, blank=True)

    def __str__(self) -> str:
        return self.name


class ProductAttribute(BaseModel):
    """
    Defines an attribute type for products, e.g. "Color", "Size", "Material".
    The attribute type controls how values are entered/displayed.
    """
    TYPE_TEXT    = "text"
    TYPE_NUMBER  = "number"
    TYPE_BOOLEAN = "boolean"
    TYPE_SELECT  = "select"
    TYPE_COLOR   = "color"

    TYPE_CHOICES = [
        (TYPE_TEXT,    "Text (free input)"),
        (TYPE_NUMBER,  "Number"),
        (TYPE_BOOLEAN, "Yes / No"),
        (TYPE_SELECT,  "Select (dropdown)"),
        (TYPE_COLOR,   "Color (color picker)"),
    ]

    COLOR_MODE_SINGLE = "single"
    COLOR_MODE_MULTI  = "multi"
    COLOR_MODE_CHOICES = [
        (COLOR_MODE_SINGLE, "Single color only"),
        (COLOR_MODE_MULTI,  "Multiple / mix colors"),
    ]

    name                 = models.CharField(max_length=255)
    code                 = models.SlugField(max_length=255, unique=True)
    data_type            = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_TEXT)
    color_mode           = models.CharField(max_length=10, choices=COLOR_MODE_CHOICES, default=COLOR_MODE_SINGLE, blank=True)
    is_variant_attribute = models.BooleanField(default=False)
    is_required          = models.BooleanField(default=False)
    deleted_at           = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.name

    @property
    def is_color_type(self):
        return self.data_type == self.TYPE_COLOR

    def save(self, *args, **kwargs):
        if self.name.strip().lower() == "color" and self.data_type != self.TYPE_COLOR:
            self.data_type = self.TYPE_COLOR
        super().save(*args, **kwargs)


class AttributeValue(BaseModel):
    """
    A concrete value/option for a ProductAttribute.
    For color attributes: hex_color + label. For others: label + value.
    """
    attribute  = models.ForeignKey(
        ProductAttribute,
        related_name="values",
        on_delete=models.CASCADE,
    )
    label      = models.CharField(max_length=255)
    value      = models.CharField(max_length=255)
    hex_color  = models.CharField(max_length=7, blank=True)
    hex_palette = models.JSONField(default=list, blank=True)
    swatch     = models.ImageField(upload_to="attributes/swatches/", blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("attribute", "value")
        ordering = ["sort_order", "label"]

    def __str__(self) -> str:
        return f"{self.attribute.name}: {self.label}"

    @property
    def color_mode(self):
        return "multi" if len(self.hex_palette or []) > 1 else "single"


# Keep for DB compatibility with existing migrations
class ProductAttributeOption(BaseModel):
    attribute  = models.ForeignKey(
        ProductAttribute,
        related_name="options",
        on_delete=models.CASCADE,
    )
    value      = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("attribute", "value")

    def __str__(self) -> str:
        return f"{self.attribute.name}: {self.value}"


def default_sale_ends_at():
    return timezone.now() + timedelta(days=534, hours=1, minutes=6, seconds=47)


class Product(BaseModel):
    TYPE_SIMPLE  = "simple"
    TYPE_VARIANT = "variant"

    STATUS_DRAFT    = "draft"
    STATUS_PENDING  = "pending_approval"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    TYPE_CHOICES = [
        (TYPE_SIMPLE,  "Simple"),
        (TYPE_VARIANT, "Variant"),
    ]

    STATUS_CHOICES = [
        (STATUS_DRAFT,    "Draft"),
        (STATUS_PENDING,  "Pending approval"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    retailer          = models.ForeignKey("retailers.Retailer", related_name="products", on_delete=models.CASCADE)
    store             = models.ForeignKey("stores.Store", related_name="products", on_delete=models.CASCADE)
    category          = models.ForeignKey(Category, related_name="products", on_delete=models.PROTECT)
    brand             = models.ForeignKey(Brand, related_name="products", null=True, blank=True, on_delete=models.SET_NULL)
    name              = models.CharField(max_length=255)
    model_name        = models.CharField(max_length=255, blank=True)
    slug              = models.SlugField(max_length=255, unique=True)
    product_type      = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_SIMPLE)
    sku               = models.CharField(max_length=100, unique=True)
    barcode           = models.CharField(max_length=120, blank=True)
    qr_code           = models.CharField(max_length=255, blank=True)
    short_description = models.CharField(max_length=320, blank=True)
    description       = models.TextField(blank=True)
    seo_title         = models.CharField(max_length=255, blank=True)
    seo_description   = models.CharField(max_length=320, blank=True)
    seo_keywords      = models.CharField(max_length=255, blank=True)
    price             = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_price    = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sale_title        = models.CharField(max_length=160, default="Hurry up! Sale ends in:", blank=True)
    sale_ends_at      = models.DateTimeField(default=default_sale_ends_at, null=True, blank=True)
    sale_override_enabled = models.BooleanField(
        default=False,
        help_text="Use this product's sale message and end time instead of global/category defaults.",
    )
    tax_rate          = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    weight            = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    length            = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    width             = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    height            = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    warranty          = models.CharField(max_length=255, blank=True)
    is_featured       = models.BooleanField(default=False)
    is_active         = models.BooleanField(default=True)
    status            = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    approved_at       = models.DateTimeField(null=True, blank=True)
    approved_by       = models.ForeignKey(
        "users.User",
        related_name="approved_products",
        null=True, blank=True,
        on_delete=models.SET_NULL,
    )
    approval_notes    = models.TextField(blank=True)
    deleted_at        = models.DateTimeField(null=True, blank=True)
    phone_variant     = models.ForeignKey(
        "catalog.PhoneModelVariant",
        related_name="products",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        help_text="Link this product listing to a specific phone model variant (e.g. iPhone 15 Pro 256GB Black).",
    )

    def __str__(self) -> str:
        return self.name

    @property
    def phone_model_display_name(self):
        if self.phone_variant and self.phone_variant.phone_model:
            return self.phone_variant.phone_model.display_name
        return self.model_name or ""

    @property
    def catalog_display_name(self):
        if self.phone_variant and self.phone_variant.phone_model:
            return self.phone_variant.phone_model.display_name
        return self.name

    def sync_phone_identity(self):
        if self.phone_variant and self.phone_variant.phone_model:
            self.model_name = self.phone_variant.phone_model.display_name
            self.name = self.phone_variant.phone_model.display_name

    def save(self, *args, **kwargs):
        from django.utils.text import slugify

        self.sync_phone_identity()

        # Auto-generate slug if not set
        if not self.slug or self.slug == '':
            base_slug = slugify(self.name)
            if not base_slug:
                base_slug = f'product-{self.id or "new"}'

            self.slug = base_slug
            counter = 1
            while Product.objects.filter(slug=self.slug).exclude(id=self.id).exists():
                self.slug = f'{base_slug}-{counter}'
                counter += 1

        super().save(*args, **kwargs)

    @property
    def default_variant(self):
        return self.variants.filter(is_default=True).first() or self.variants.first()

    @property
    def primary_image(self):
        items = list(self.media_items.all())
        img = next((asset for asset in items if asset.media_type == "image" and asset.is_primary), None)
        if not img:
            img = next((asset for asset in items if asset.media_type == "image"), None)
        return img.file if img and img.file else None

    @property
    def discount_percentage(self):
        if self.discount_price and self.price and self.price > 0 and self.discount_price < self.price:
            return int(((self.price - self.discount_price) / self.price) * 100)
        return 0

    @property
    def available_qty(self):
        variant_ids = list(self.variants.values_list("id", flat=True))
        stock_qs = self.stock_items.filter(variant_id__in=variant_ids) if variant_ids else self.stock_items.filter(variant__isnull=True)
        aggregate = stock_qs.aggregate(
            on_hand=models.Sum("on_hand_quantity"),
            reserved=models.Sum("reserved_quantity"),
        )
        on_hand = aggregate["on_hand"] or 0
        reserved = aggregate["reserved"] or 0
        return max(0, on_hand - reserved)

    @property
    def storefront_stock_snapshot(self):
        available = self.available_qty
        if available > 0:
            return {"label": "Available Stock", "tone": "success", "available": available, "icon": "fa-circle-check"}
        return {"label": "Out of Stock", "tone": "danger", "available": 0, "icon": "fa-circle-xmark"}

    @property
    def storefront_stock_label(self):
        return self.storefront_stock_snapshot["label"]

    @property
    def storefront_stock_tone(self):
        return self.storefront_stock_snapshot["tone"]

    @property
    def quickview_variant_labels(self):
        labels = []
        seen = {}

        def storage_sort_value(label):
            import re
            match = re.search(r'(\d+)\s*(GB|TB|MB)', label or "", re.IGNORECASE)
            if match:
                val = int(match.group(1))
                unit = match.group(2).upper()
                if unit == 'TB':
                    return val * 1024
                if unit == 'MB':
                    return val / 1024
                return val
            return 0
        
        def add_normalized(val, has_stock=True):
            val_clean = (val or "").strip()
            if not val_clean:
                return
            # Normalize to remove spaces in storage like '128 GB' -> '128GB'
            norm = val_clean.replace(" ", "").upper()
            if norm not in seen:
                seen[norm] = {"label": norm, "has_stock": bool(has_stock)}
                labels.append(norm)
            else:
                seen[norm]["has_stock"] = seen[norm]["has_stock"] or bool(has_stock)

        if self.phone_variant and self.phone_variant.storage:
            add_normalized(self.phone_variant.storage)
            
        variants = sorted(self.variants.all(), key=lambda item: (item.available_qty <= 0, storage_sort_value(item.name), item.name.lower()))
        for variant in variants:
            storage_val = variant.attribute_values.filter(attribute__name__icontains="storage").first()
            if storage_val and storage_val.value:
                add_normalized(storage_val.value, variant.available_qty > 0)
            else:
                label = (variant.name or "").strip()
                if " / " in label:
                    label = label.split(" / ")[0].strip()
                elif "/" in label:
                    label = label.split("/")[0].strip()
                elif "–" in label:
                    label = label.split("–")[0].strip()
                add_normalized(label, variant.available_qty > 0)
                
        if not labels:
            pa = self.attribute_assignments.filter(attribute__name__icontains="storage").first()
            if pa:
                for val in pa.chosen_values.all():
                    add_normalized(val.label)
                
        if labels:
            labels.sort(key=lambda norm: (not seen[norm]["has_stock"], storage_sort_value(seen[norm]["label"])))
            return [seen[norm]["label"] for norm in labels]
            
        return ["Default"]

    @property
    def quickview_rams(self):
        rams = []
        seen = {}

        def ram_sort_value(label):
            import re
            match = re.search(r'(\d+)\s*(GB|MB)', label or "", re.IGNORECASE)
            if match:
                val = int(match.group(1))
                unit = match.group(2).upper()
                if unit == 'GB':
                    return val * 1024
                return val
            return 0
        
        def add_normalized(val, has_stock=True):
            val_clean = (val or "").strip()
            if not val_clean:
                return
            norm = val_clean.replace(" ", "").upper()
            if norm not in seen:
                seen[norm] = {"label": norm, "has_stock": bool(has_stock)}
                rams.append(norm)
            else:
                seen[norm]["has_stock"] = seen[norm]["has_stock"] or bool(has_stock)

        if self.phone_variant and self.phone_variant.ram:
            add_normalized(self.phone_variant.ram)
            
        variants = sorted(self.variants.all(), key=lambda item: (item.available_qty <= 0, ram_sort_value(item.name), item.name.lower()))
        for variant in variants:
            ram_val = variant.attribute_values.filter(attribute__name__icontains="ram").first()
            if ram_val and ram_val.value:
                add_normalized(ram_val.value, variant.available_qty > 0)
                
        if not rams:
            pa = self.attribute_assignments.filter(attribute__name__icontains="ram").first()
            if pa:
                for val in pa.chosen_values.all():
                    add_normalized(val.label)
                
        if rams:
            rams.sort(key=lambda norm: (not seen[norm]["has_stock"], ram_sort_value(seen[norm]["label"])))
            return [seen[norm]["label"] for norm in rams]
            
        return []

    @property
    def quickview_color_data(self):
        colors = []
        seen = {}
        
        def add_color(label, hex_val, has_stock=True):
            label_clean = (label or "").strip()
            if not label_clean:
                return
            hex_clean = (hex_val or "#cccccc").strip()
            key = label_clean.lower()
            if key not in seen:
                seen[key] = {"label": label_clean, "hex": hex_clean, "has_stock": bool(has_stock)}
                colors.append(key)
            else:
                seen[key]["has_stock"] = seen[key]["has_stock"] or bool(has_stock)

        if self.phone_variant and self.phone_variant.color:
            add_color(self.phone_variant.color, self.phone_variant.color_hex)
            
        variants = sorted(self.variants.all(), key=lambda item: (item.available_qty <= 0, item.name.lower()))
        for variant in variants:
            color_val = variant.attribute_values.filter(attribute__name__icontains="color").first()
            if color_val and color_val.value:
                hex_color = "#cccccc"
                color_source = AttributeValue.objects.filter(attribute__name__icontains="color", label__iexact=color_val.value.strip()).first()
                if color_source:
                    hex_color = color_source.hex_color or "#cccccc"
                elif self.phone_variant and self.phone_variant.color.lower() == color_val.value.strip().lower():
                    hex_color = self.phone_variant.color_hex or "#cccccc"
                add_color(color_val.value, hex_color, variant.available_qty > 0)
                
        pa = self.attribute_assignments.filter(attribute__name__icontains="color").first()
        if pa:
            for val in pa.chosen_values.all():
                add_color(val.label, val.hex_color or "#cccccc")
                
        colors.sort(key=lambda key: not seen[key]["has_stock"])
        return [f"{seen[key]['label']}:{seen[key]['hex']}" for key in colors]

    @property
    def quickview_colors(self):
        colors = []
        seen = {}
        
        def add_color(label, hex_val, has_stock=True):
            label_clean = (label or "").strip()
            if not label_clean:
                return
            hex_clean = (hex_val or "#cccccc").strip()
            key = label_clean.lower()
            if key not in seen:
                # Find matching image URL for this color
                color_img = self.media_items.filter(media_type="image", color__iexact=label_clean).first()
                img_url = color_img.file.url if color_img and color_img.file else (self.primary_image.url if self.primary_image else "")
                seen[key] = {
                    "name": label_clean,
                    "hex": hex_clean,
                    "image_url": img_url,
                    "has_stock": bool(has_stock),
                }
                colors.append(key)
            else:
                seen[key]["has_stock"] = seen[key]["has_stock"] or bool(has_stock)

        if self.phone_variant and self.phone_variant.color:
            add_color(self.phone_variant.color, self.phone_variant.color_hex)
            
        variants = sorted(self.variants.all(), key=lambda item: (item.available_qty <= 0, item.name.lower()))
        for variant in variants:
            color_val = variant.attribute_values.filter(attribute__name__icontains="color").first()
            if color_val and color_val.value:
                hex_color = "#cccccc"
                color_source = AttributeValue.objects.filter(attribute__name__icontains="color", label__iexact=color_val.value.strip()).first()
                if color_source:
                    hex_color = color_source.hex_color or "#cccccc"
                elif self.phone_variant and self.phone_variant.color.lower() == color_val.value.strip().lower():
                    hex_color = self.phone_variant.color_hex or "#cccccc"
                add_color(color_val.value, hex_color, variant.available_qty > 0)
                
        pa = self.attribute_assignments.filter(attribute__name__icontains="color").first()
        if pa:
            for val in pa.chosen_values.all():
                add_color(val.label, val.hex_color or "#cccccc")
                
        colors.sort(key=lambda key: not seen[key]["has_stock"])
        return [
            {"name": seen[key]["name"], "hex": seen[key]["hex"], "image_url": seen[key]["image_url"]}
            for key in colors
        ]

    @property
    def quickview_image_urls(self):
        urls = []
        for media in self.media_items.all():
            if getattr(media, "media_type", "") != "image" or not getattr(media, "file", None):
                continue
            url = media.file.url
            if url not in urls:
                urls.append(url)
        if self.primary_image:
            primary_url = self.primary_image.url
            if primary_url not in urls:
                urls.insert(0, primary_url)
        return urls[:8]

    @property
    def quickview_image_colors(self):
        urls_seen = set()
        colors = []
        
        # Primary image first if exists
        if self.primary_image:
            primary_url = self.primary_image.url
            urls_seen.add(primary_url)
            media = self.media_items.filter(file=self.primary_image.name).first()
            colors.append(media.color if media and media.color else "")
            
        for media in self.media_items.all():
            if getattr(media, "media_type", "") != "image" or not getattr(media, "file", None):
                continue
            url = media.file.url
            if url not in urls_seen:
                urls_seen.add(url)
                colors.append(media.color if media.color else "")
                
        return colors[:8]

    @property
    def variants_json(self):
        import json
        import re
        variant_list = []

        def variant_storage_size(variant):
            storage_value = ""
            storage_attr = variant.attribute_values.filter(attribute__name__icontains="storage").first()
            if storage_attr and storage_attr.value:
                storage_value = storage_attr.value
            else:
                storage_value = variant.name
            match = re.search(r'(\d+)\s*(GB|TB|MB)', storage_value or "", re.IGNORECASE)
            if not match:
                return 0
            val = int(match.group(1))
            unit = match.group(2).upper()
            if unit == "TB":
                return val * 1024
            if unit == "MB":
                return val / 1024
            return val

        variants = sorted(self.variants.all(), key=lambda item: (item.available_qty <= 0, variant_storage_size(item), item.name.lower()))
        for variant in variants:
            attrs = {}
            for av in variant.attribute_values.all():
                if av.attribute:
                    attrs[av.attribute.name.lower()] = av.value.lower()
            variant_list.append({
                "id": str(variant.id),
                "sku": variant.sku,
                "price": str(variant.discount_price or variant.price),
                "compare_price": str(variant.price) if variant.discount_price else "",
                "stock": variant.available_qty,
                "attributes": attrs
            })
        return json.dumps(variant_list)


class ProductAttributeAssignment(BaseModel):
    """Links a Product to its selected ProductAttributes and their chosen values."""
    product       = models.ForeignKey(Product, related_name="attribute_assignments", on_delete=models.CASCADE)
    attribute     = models.ForeignKey(ProductAttribute, related_name="product_assignments", on_delete=models.CASCADE)
    text_value    = models.CharField(max_length=500, blank=True)
    chosen_values = models.ManyToManyField(
        AttributeValue,
        related_name="product_assignments",
        blank=True,
    )

    class Meta:
        unique_together = ("product", "attribute")

    def __str__(self) -> str:
        return f"{self.product.name} → {self.attribute.name}"


# ─── Phone Platform / Model / Variant Hierarchy ───────────────────────────────

class PhonePlatform(BaseModel):
    """Top-level device family: phone, tablet, or laptop."""
    APPLE   = "apple"
    ANDROID = "android"
    LAPTOP  = "laptop"
    PLATFORM_CHOICES = [
        (APPLE,   "Phone"),
        (ANDROID, "Tablet"),
        (LAPTOP,  "Laptop"),
    ]
    name = models.CharField(max_length=50, choices=PLATFORM_CHOICES, unique=True)

    @property
    def display_name(self) -> str:
        return self.get_name_display()

    def __str__(self) -> str:
        return self.display_name


class PhoneBrand(BaseModel):
    """Android-only brand (e.g. Samsung, OnePlus, Xiaomi)."""
    platform    = models.ForeignKey(PhonePlatform, related_name="brands", on_delete=models.CASCADE)
    name        = models.CharField(max_length=100)
    slug        = models.SlugField(max_length=120, unique=True)
    logo        = models.ImageField(upload_to="phone_brands/", blank=True)
    sort_order  = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("platform", "name")
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class PhoneModel(BaseModel):
    """A phone model, e.g. 'iPhone 15 Pro' (Apple) or 'Galaxy S24' (Samsung)."""
    platform    = models.ForeignKey(PhonePlatform, related_name="models", on_delete=models.CASCADE)
    brand       = models.ForeignKey(
        PhoneBrand,
        related_name="models",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        help_text="Required for Android phones. Leave blank for Apple.",
    )
    name        = models.CharField(max_length=255, help_text="Model name, e.g. 'iPhone 15 Pro' or 'Galaxy S24+'")
    slug        = models.SlugField(max_length=280, unique=True)
    released_year = models.PositiveSmallIntegerField(null=True, blank=True)
    sort_order  = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["platform", "brand__name", "sort_order", "name"]

    @property
    def display_name(self) -> str:
        if self.brand:
            if self.name.strip().lower().startswith(self.brand.name.strip().lower()):
                return self.name
            return f"{self.brand.name} {self.name}"
        return self.name

    def __str__(self) -> str:
        return self.display_name

    def save(self, *args, **kwargs):
        from django.utils.text import slugify
        if not self.slug:
            base_slug = slugify(self.display_name)
            self.slug = base_slug
            counter = 1
            while PhoneModel.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{base_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)


class PhoneStorageOption(BaseModel):
    label = models.CharField(max_length=30, unique=True, help_text="e.g. 128GB, 256GB, 1TB")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "label"]

    def __str__(self) -> str:
        return self.label


class PhoneRamOption(BaseModel):
    label = models.CharField(max_length=30, unique=True, help_text="e.g. 4GB, 8GB, 16GB")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "label"]

    def __str__(self) -> str:
        return self.label


class PhoneColorOption(BaseModel):
    name = models.CharField(max_length=80, unique=True, help_text="e.g. Midnight Black, Starlight")
    color_hex = models.CharField(max_length=7, blank=True, help_text="#rrggbb")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class PhoneModelVariant(BaseModel):
    """A specific storage/colour variant of a PhoneModel.

    Admin creates these globally; retailers then link their Products to one.
    E.g. 'iPhone 15 Pro – 256 GB – Titanium Black'
    """
    phone_model = models.ForeignKey(PhoneModel, related_name="variants", on_delete=models.CASCADE)
    ram         = models.CharField(max_length=30, blank=True, help_text="e.g. 8GB, 16GB")
    storage     = models.CharField(max_length=30, blank=True, help_text="e.g. 128GB, 256GB, 1TB")
    color       = models.CharField(max_length=80, blank=True, help_text="e.g. Midnight Black, Starlight")
    color_hex   = models.CharField(max_length=7, blank=True, help_text="#rrggbb")
    sort_order  = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "ram", "storage", "color"]

    @property
    def display_name(self) -> str:
        parts = [p for p in [self.ram, self.storage, self.color] if p]
        return " / ".join(parts) or "Default"

    @property
    def full_name(self) -> str:
        return f"{self.phone_model.display_name} – {self.display_name}"

    def __str__(self) -> str:
        return self.full_name


class ProductVariant(BaseModel):

    """
    Simplified: only a name field shown to retailers.
    SKU is auto-generated. Price & barcode optionally set.
    """
    product        = models.ForeignKey(Product, related_name="variants", on_delete=models.CASCADE)
    name           = models.CharField(max_length=255)
    sku            = models.CharField(max_length=100, unique=True)
    barcode        = models.CharField(max_length=120, blank=True)
    price          = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_default     = models.BooleanField(default=False)
    deleted_at     = models.DateTimeField(null=True, blank=True)

    @property
    def available_qty(self):
        from apps.inventory.models import StockItem
        aggregate = StockItem.objects.filter(variant=self).aggregate(
            on_hand=models.Sum("on_hand_quantity"),
            reserved=models.Sum("reserved_quantity")
        )
        on_hand = aggregate["on_hand"] or 0
        reserved = aggregate["reserved"] or 0
        return max(0, on_hand - reserved)

    def __str__(self) -> str:
        return f"{self.product.name} / {self.name}"


class ProductVariantAttributeValue(BaseModel):
    """Kept for DB compatibility only."""
    variant   = models.ForeignKey(ProductVariant, related_name="attribute_values", on_delete=models.CASCADE)
    attribute = models.ForeignKey(ProductAttribute, related_name="variant_values", on_delete=models.CASCADE)
    option    = models.ForeignKey(
        ProductAttributeOption,
        related_name="variant_values",
        null=True, blank=True,
        on_delete=models.SET_NULL,
    )
    value     = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("variant", "attribute")


class ProductMedia(BaseModel):
    TYPE_IMAGE    = "image"
    TYPE_VIDEO    = "video"
    TYPE_IMAGE_360 = "image_360"

    TYPE_CHOICES = [
        (TYPE_IMAGE,    "Image"),
        (TYPE_VIDEO,    "Video"),
        (TYPE_IMAGE_360, "360 Image"),
    ]

    product      = models.ForeignKey(Product, related_name="media_items", on_delete=models.CASCADE)
    variant      = models.ForeignKey(
        ProductVariant,
        related_name="media_items",
        null=True, blank=True,
        on_delete=models.CASCADE,
    )
    media_type   = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_IMAGE)
    title        = models.CharField(max_length=255, blank=True)
    alt_text     = models.CharField(max_length=255, blank=True)
    file         = models.FileField(upload_to="products/media/", blank=True)
    external_url = models.URLField(blank=True)
    is_primary   = models.BooleanField(default=False)
    sort_order   = models.PositiveIntegerField(default=0)
    color        = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self) -> str:
        return f"{self.product.name} / {self.media_type}"

    @property
    def embed_url(self):
        url = self.external_url
        if not url:
            return ""
        if "youtube.com/watch" in url:
            video_id = url.split("v=")[-1].split("&")[0]
            return f"https://www.youtube.com/embed/{video_id}"
        elif "shorts/" in url:
            video_id = url.split("shorts/")[-1].split("?")[0]
            return f"https://www.youtube.com/embed/{video_id}"
        elif "youtu.be/" in url:
            video_id = url.split("youtu.be/")[-1].split("?")[0]
            return f"https://www.youtube.com/embed/{video_id}"
        elif "vimeo.com/" in url:
            video_id = url.split("vimeo.com/")[-1].split("?")[0]
            return f"https://player.vimeo.com/video/{video_id}"
        return url


class MediaLibrary(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="media_assets",
        on_delete=models.CASCADE,
    )
    file = models.FileField(upload_to="media_library/")
    filename = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(default=0)

    def save(self, *args, **kwargs):
        if self.file and not self.filename:
            import os
            self.filename = os.path.basename(self.file.name)
            try:
                self.file_size = self.file.size
            except Exception:
                pass
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} / {self.filename or self.id}"


class ProductReview(BaseModel):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    product = models.ForeignKey(Product, related_name="reviews", on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    reviewer_name = models.CharField(max_length=255)
    rating = models.PositiveIntegerField(default=5)
    comment = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    def __str__(self) -> str:
        return f"{self.product.name} - {self.title} ({self.rating} stars)"
