import json

from django import forms
from django.utils.text import slugify

from apps.catalog.models import (
    AttributeValue,
    Category,
    Product,
    ProductAttribute,
    ProductAttributeAssignment,
    ProductMedia,
    ProductVariant,
    ProductVariantAttributeValue,
    PhoneColorOption,
    PhoneModelVariant,
)
from apps.catalog.services import unique_sku
from apps.stores.models import Store
from apps.marketplace.models import MarketplaceConnection, MarketplaceListing


# ─── Attribute Management Forms ──────────────────────────────────────────────

class ProductAttributeForm(forms.ModelForm):
    class Meta:
        model = ProductAttribute
        fields = ["name", "data_type", "color_mode", "is_variant_attribute", "is_required"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Allow name to be edited even when updating
        self.fields['name'].disabled = False

    def clean(self):
        cleaned_data = super().clean()
        if (cleaned_data.get("name") or "").strip().lower() == "color":
            cleaned_data["data_type"] = ProductAttribute.TYPE_COLOR
        if cleaned_data.get("data_type") != ProductAttribute.TYPE_COLOR:
            cleaned_data["color_mode"] = ProductAttribute.COLOR_MODE_SINGLE
        return cleaned_data

    def save(self, commit=True):
        obj = super().save(commit=False)

        # Check if name has changed (only for existing attributes)
        name_changed = False
        if self.instance.pk:
            try:
                original = ProductAttribute.objects.get(pk=self.instance.pk)
                name_changed = original.name != obj.name
            except ProductAttribute.DoesNotExist:
                name_changed = False

        # Only update code if it's a new attribute or name has changed
        if not obj.code or name_changed:
            new_code = slugify(obj.name)
            # Ensure unique code
            base = new_code
            counter = 1
            qs = ProductAttribute.objects.exclude(pk=obj.pk)
            while qs.filter(code=new_code).exists():
                new_code = f"{base}-{counter}"
                counter += 1
            obj.code = new_code

        if commit:
            obj.save()
        return obj


class AttributeValueForm(forms.ModelForm):
    class Meta:
        model = AttributeValue
        fields = ["label", "value", "hex_color", "swatch", "sort_order"]
        widgets = {
            "hex_color": forms.TextInput(attrs={"type": "color"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        attribute = self.instance.attribute if self.instance.pk else self.initial.get("attribute")
        if attribute and attribute.data_type == ProductAttribute.TYPE_COLOR:
            cleaned_data["value"] = cleaned_data.get("value") or cleaned_data.get("label")
            if not cleaned_data.get("hex_color"):
                self.add_error("hex_color", "Color picker value is required for color options.")
            cleaned_data["hex_palette"] = [cleaned_data["hex_color"]]
        return cleaned_data


# ─── Product Form ─────────────────────────────────────────────────────────────

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single_clean = super().clean
        if data in self.empty_values:
            return []
        if isinstance(data, (list, tuple)):
            return [single_clean(item, initial) for item in data]
        return [single_clean(data, initial)]

class ProductForm(forms.ModelForm):
    SALE_MODE_CHOICES = (
        ("global", "Use global / category countdown"),
        ("manual", "Use manual product countdown"),
    )
    sale_mode = forms.ChoiceField(choices=SALE_MODE_CHOICES, required=False, label="Countdown mode")
    phone_variant_id = forms.ModelChoiceField(
        queryset=PhoneModelVariant.objects.select_related("phone_model", "phone_model__brand").all(),
        required=False,
        widget=forms.HiddenInput(),
        label="Device Variant",
    )
    variants_payload = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        label="Product Variants Payload",
    )
    product_images = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={"multiple": True, "accept": "image/*"}),
        label="Product Images",
    )
    product_videos = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={"multiple": True, "accept": "video/*"}),
        label="Product Videos",
    )
    product_360_images = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={"multiple": True, "accept": "image/*"}),
        label="360 Images",
    )
    product_video_urls = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "One video URL per line"}),
        label="External Video URLs",
    )
    default_variant = forms.ModelChoiceField(
        queryset=ProductVariant.objects.none(),
        required=False,
        empty_label="Choose default variant",
        label="Default Variant",
    )
    remove_asset_ids = forms.ModelMultipleChoiceField(
        queryset=ProductMedia.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Remove Existing Assets",
    )
    amazon_seller_sku = forms.CharField(
        required=False,
        label="Amazon Seller SKU",
        max_length=120,
        widget=forms.TextInput(attrs={"placeholder": "Leave blank to use the Nuboxed SKU"}),
        help_text="Use the exact SKU shown in Amazon Seller Central for this marketplace.",
    )
    amazon_asin = forms.CharField(
        required=False,
        label="Amazon ASIN",
        max_length=20,
        widget=forms.TextInput(attrs={"placeholder": "Example: B0CVJ8716B"}),
        help_text="Add the ASIN to enable reliable France listing and offer updates.",
    )

    class Meta:
        model = Product
        fields = [
            "store", "category", "brand",
            "name", "model_name",
            "barcode",
            "short_description", "description",
            "price", "discount_price", "sale_title", "sale_ends_at", "sale_override_enabled", "tax_rate",
            "product_type",
            "weight", "length", "width", "height",
            "warranty",
            "is_featured", "is_active",
        ]

    def __init__(self, *args, store_queryset=None, **kwargs):
        allow_sale_countdown = kwargs.pop("allow_sale_countdown", True)
        allow_sale_message = kwargs.pop("allow_sale_message", True)
        super().__init__(*args, **kwargs)
        self._store_queryset = store_queryset
        connection = MarketplaceConnection.objects.filter(connector__code="amazon").first()
        if connection and getattr(self.instance, "pk", None):
            listing = MarketplaceListing.objects.filter(
                connection=connection, product=self.instance, variant=None,
            ).order_by("-external_listing_id", "-updated_at").first()
            if listing:
                self.initial["amazon_seller_sku"] = listing.seller_sku
                self.initial["amazon_asin"] = listing.external_listing_id
        if "sale_mode" in self.fields:
            self.fields["sale_mode"].initial = "manual" if getattr(self.instance, "sale_override_enabled", False) else "global"
        if not allow_sale_countdown:
            for field_name in ("sale_mode", "sale_title", "sale_ends_at", "sale_override_enabled"):
                self.fields.pop(field_name, None)
        elif not allow_sale_message:
            self.fields.pop("sale_title", None)
        if "sale_ends_at" in self.fields:
            self.fields["sale_ends_at"].widget = forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local"},
            )
            self.fields["sale_ends_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]
        self.fields["category"].queryset = Category.objects.filter(is_active=True).select_related("parent").order_by("parent__name", "sort_order", "name")
        self.fields["category"].label_from_instance = self._category_label
        if store_queryset is not None:
            if "store" in self.fields:
                self.fields["store"].widget = forms.HiddenInput()
                self.fields["store"].required = False
                if self.instance and getattr(self.instance, "store_id", None):
                    self.fields["store"].initial = self.instance.store
                elif store_queryset.exists():
                    self.fields["store"].initial = store_queryset.first()
            for field_name in ("price", "discount_price", "product_video_urls"):
                if field_name in self.fields:
                    self.fields[field_name].widget = forms.HiddenInput()
                    self.fields[field_name].required = False
        if "phone_variant_id" in self.fields:
            self.fields["phone_variant_id"].queryset = PhoneModelVariant.objects.select_related("phone_model", "phone_model__brand").all()
            if self.instance and getattr(self.instance, "phone_variant_id", None):
                self.fields["phone_variant_id"].initial = self.instance.phone_variant
        if "variants_payload" in self.fields:
            if self.instance and self.instance.pk:
                variants_payload = []
                for variant in self.instance.variants.filter(deleted_at__isnull=True).order_by("-is_default", "created_at"):
                    model_id = ""
                    ram_value = ""
                    storage_value = ""
                    color_value = ""
                    color_hex = ""
                    phone_model = getattr(getattr(self.instance, "phone_variant", None), "phone_model", None)
                    if phone_model:
                        model_id = str(phone_model.id)
                    ram_attr = ProductAttribute.objects.filter(code__iexact="ram").first()
                    storage_attr = ProductAttribute.objects.filter(code__iexact="storage").first()
                    color_attr = ProductAttribute.objects.filter(code__iexact="color").first()
                    if ram_attr:
                        ram_mapping = variant.attribute_values.filter(attribute=ram_attr).first()
                        if ram_mapping:
                            ram_value = ram_mapping.value or ""
                    if storage_attr:
                        storage_mapping = variant.attribute_values.filter(attribute=storage_attr).first()
                        if storage_mapping:
                            storage_value = storage_mapping.value or ""
                    if color_attr:
                        color_mapping = variant.attribute_values.filter(attribute=color_attr).first()
                        if color_mapping:
                            color_value = color_mapping.value or ""
                    if phone_model and (ram_value or storage_value or color_value):
                        matched_phone_variant = PhoneModelVariant.objects.filter(
                            phone_model=phone_model,
                            ram__iexact=ram_value,
                            storage__iexact=storage_value,
                            color__iexact=color_value,
                        ).first()
                        if matched_phone_variant:
                            color_hex = matched_phone_variant.color_hex or ""
                    stock_item = (
                        variant.stock_items.select_related("warehouse")
                        .order_by("-warehouse__is_default", "-created_at")
                        .first()
                    )
                    amazon_mapping = None
                    try:
                        amazon_mapping = MarketplaceListing.objects.filter(
                            product=self.instance, variant=variant,
                            connection__connector__code="amazon",
                        ).order_by("-updated_at").first()
                    except Exception:
                        amazon_mapping = None
                    variants_payload.append({
                        "id": str(variant.id),
                        "name": variant.name,
                        "sku": variant.sku,
                        "barcode": variant.barcode,
                        "price": str(variant.price),
                        "discount_price": str(variant.discount_price) if variant.discount_price is not None else "",
                        "is_default": variant.is_default,
                        "quantity": str(stock_item.available_quantity if stock_item else 0),
                        "model_id": model_id,
                        "ram": ram_value,
                        "storage": storage_value,
                        "color": color_value,
                        "color_hex": color_hex,
                        "amazon_seller_sku": amazon_mapping.seller_sku if amazon_mapping else "",
                        "amazon_asin": amazon_mapping.external_listing_id if amazon_mapping else "",
                    })
                self.fields["variants_payload"].initial = json.dumps(variants_payload)
            else:
                self.fields["variants_payload"].initial = "[]"
        if store_queryset is not None:
            self.fields["store"].queryset = store_queryset
        else:
            self.fields["store"].queryset = Store.objects.all()

        # Dynamically load all active ProductAttributes (real-time attributes)
        attrs = ProductAttribute.objects.prefetch_related("values").all()
        for attr in attrs:
            if attr.is_variant_attribute or attr.code == "storage" or attr.name.strip().lower() in {"internal storage", "storage"}:
                continue
            field_name = f"attr_{attr.code}"
            values = attr.values.all()
            choices = [("", f"Select {attr.name}")]
            choices.extend((str(val.id), val.label) for val in values)

            initial_val = ""
            if self.instance and self.instance.pk:
                assignment = ProductAttributeAssignment.objects.filter(product=self.instance, attribute=attr).first()
                if assignment:
                    chosen_value = assignment.chosen_values.first()
                    if chosen_value:
                        initial_val = str(chosen_value.id)
            
            self.fields[field_name] = forms.ChoiceField(
                choices=choices,
                required=attr.is_required,
                initial=initial_val,
                label=attr.name
            )
            self.fields[field_name].widget.attrs["class"] = "ra-input"

        if self.instance and self.instance.pk:
            variants = self.instance.variants.order_by("name")
            assets = self.instance.media_items.order_by("sort_order", "title")
            self.fields["default_variant"].queryset = variants
            self.fields["remove_asset_ids"].queryset = assets
            current_default = self.instance.default_variant
            if current_default:
                self.fields["default_variant"].initial = current_default
            
            # Populate initial external video URLs
            ext_videos = assets.filter(media_type=ProductMedia.TYPE_VIDEO).exclude(external_url="")
            if ext_videos.exists():
                self.fields["product_video_urls"].initial = "\n".join(v.external_url for v in ext_videos)
        else:
            self.fields["default_variant"].widget = forms.HiddenInput()
            self.fields["remove_asset_ids"].widget = forms.MultipleHiddenInput()

    def clean(self):
        cleaned = super().clean()
        if "sale_mode" in self.fields:
            cleaned["sale_override_enabled"] = cleaned.get("sale_mode") == "manual"
        store = cleaned.get("store")
        if not store and getattr(self, "_store_queryset", None) is not None:
            store = self._store_queryset.first()
            if store:
                cleaned["store"] = store
        try:
            rows = json.loads(cleaned.get("variants_payload") or "[]")
        except json.JSONDecodeError:
            rows = []
        if not cleaned.get("price"):
            for row in rows:
                price_value = (row.get("price") or "").strip()
                if price_value:
                    cleaned["price"] = price_value
                    break
        if not cleaned.get("discount_price"):
            for row in rows:
                discount_value = (row.get("discount_price") or "").strip()
                if discount_value:
                    cleaned["discount_price"] = discount_value
                    break
        return cleaned

    def _category_label(self, obj):
        if obj.parent_id and obj.parent:
            return f"{obj.parent.name} / {obj.name}"
        return obj.name

    def save_product_attributes(self, product):
        from apps.catalog.models import AttributeValue, ProductAttribute, ProductAttributeAssignment

        if not product.pk:
            return

        for attr in ProductAttribute.objects.all():
            field_name = f"attr_{attr.code}"
            val_id = self.cleaned_data.get(field_name)
            if not val_id:
                ProductAttributeAssignment.objects.filter(product=product, attribute=attr).delete()
                continue

            val_obj = AttributeValue.objects.filter(id=val_id, attribute=attr).first()
            if not val_obj:
                continue

            assignment, _ = ProductAttributeAssignment.objects.get_or_create(
                product=product,
                attribute=attr,
            )
            assignment.chosen_values.set([val_obj])

    def sync_product_variants(self, product):
        if not product or not product.pk:
            return
        from apps.inventory.services import sync_product_stock
        try:
            rows = json.loads(self.cleaned_data.get("variants_payload") or "[]")
        except json.JSONDecodeError:
            rows = []

        existing = {str(item.id): item for item in product.variants.all()}
        keep_ids = set()
        storage_attr = ProductAttribute.objects.filter(code__iexact="storage").first()
        if not storage_attr:
            storage_attr = ProductAttribute.objects.create(
                code="storage",
                name="Storage",
                data_type=ProductAttribute.TYPE_SELECT,
                is_variant_attribute=True,
            )
        color_attr, _ = ProductAttribute.objects.get_or_create(
            code="color",
            defaults={
                "name": "Color",
                "data_type": ProductAttribute.TYPE_COLOR,
                "is_variant_attribute": True,
            },
        )
        ram_attr, _ = ProductAttribute.objects.get_or_create(
            code="ram",
            defaults={
                "name": "RAM",
                "data_type": ProductAttribute.TYPE_SELECT,
                "is_variant_attribute": True,
            },
        )
        for row in rows:
            name = (row.get("name") or "").strip()
            if not name:
                continue

            row_id = str(row.get("id") or "").strip()
            variant = existing.get(row_id) if row_id in existing else ProductVariant(product=product)
            variant.name = name
            sku = (row.get("sku") or "").strip()
            variant.sku = sku or variant.sku or unique_sku(ProductVariant, f"{product.sku}-{name}")
            variant.barcode = (row.get("barcode") or "").strip()
            variant.price = row.get("price") or product.price
            discount_price = row.get("discount_price")
            variant.discount_price = discount_price if discount_price not in ("", None) else None
            variant.is_default = bool(row.get("is_default"))
            variant.product = product
            variant.save()
            try:
                from apps.marketplace.services import sync_product_amazon_mapping
                sync_product_amazon_mapping(
                    product, row.get("amazon_seller_sku", ""),
                    row.get("amazon_asin", ""), variant=variant,
                )
            except Exception:
                # Amazon mapping is optional during a local product edit.
                pass
            storage_value = (row.get("storage") or "").strip()
            if storage_value:
                ProductVariantAttributeValue.objects.update_or_create(
                    variant=variant,
                    attribute=storage_attr,
                    defaults={"value": storage_value},
                )
            else:
                ProductVariantAttributeValue.objects.filter(variant=variant, attribute=storage_attr).delete()
            color_value = (row.get("color") or "").strip()
            if color_value:
                ProductVariantAttributeValue.objects.update_or_create(
                    variant=variant,
                    attribute=color_attr,
                    defaults={"value": color_value},
                )
            else:
                ProductVariantAttributeValue.objects.filter(variant=variant, attribute=color_attr).delete()
            ram_value = (row.get("ram") or "").strip()
            if ram_value:
                ProductVariantAttributeValue.objects.update_or_create(
                    variant=variant,
                    attribute=ram_attr,
                    defaults={"value": ram_value},
                )
            else:
                ProductVariantAttributeValue.objects.filter(variant=variant, attribute=ram_attr).delete()
            quantity_raw = row.get("quantity")
            try:
                quantity = int(quantity_raw or 0)
            except (TypeError, ValueError):
                quantity = 0
            sync_product_stock(product=product, variant=variant, available_quantity=quantity)
            if variant.is_default:
                product.variants.exclude(id=variant.id).update(is_default=False)
            keep_ids.add(str(variant.id))

        for variant in product.variants.all():
            if str(variant.id) not in keep_ids:
                variant.delete()

        if product.variants.exists() and not product.variants.filter(is_default=True).exists():
            first = product.variants.order_by("-is_default", "created_at").first()
            if first:
                first.is_default = True
                first.save(update_fields=["is_default", "updated_at"])

    def resolve_phone_variant_from_payload(self):
        phone_variant = self.cleaned_data.get("phone_variant_id")
        if phone_variant:
            return phone_variant
        try:
            rows = json.loads(self.cleaned_data.get("variants_payload") or "[]")
        except json.JSONDecodeError:
            rows = []

        for row in rows:
            model_id = (row.get("model_id") or "").strip()
            ram = (row.get("ram") or "").strip()
            storage = (row.get("storage") or "").strip()
            color = (row.get("color") or "").strip()
            if not model_id or (not ram and not storage and not color):
                continue
            color_hex = ""
            if color:
                color_option = PhoneColorOption.objects.filter(name__iexact=color).first()
                if color_option:
                    color_hex = color_option.color_hex or ""
            phone_variant = PhoneModelVariant.objects.filter(
                phone_model_id=model_id,
                ram=ram,
                storage=storage,
                color=color,
            ).first()
            if not phone_variant:
                phone_variant = PhoneModelVariant.objects.create(
                    phone_model_id=model_id,
                    ram=ram,
                    storage=storage,
                    color=color,
                    color_hex=color_hex,
                )
            if color_hex and phone_variant.color_hex != color_hex:
                phone_variant.color_hex = color_hex
                phone_variant.save(update_fields=["color_hex", "updated_at"])
            return phone_variant
        return None

    def save(self, commit=True):
        product = super().save(commit=False)
        
        # Ensure store is never None
        if not getattr(product, "store_id", None):
            if self.instance and self.instance.pk:
                old_store = Product.objects.filter(pk=self.instance.pk).values_list("store_id", flat=True).first()
                if old_store:
                    product.store_id = old_store
            elif getattr(self, "_store_queryset", None) and self._store_queryset.exists():
                product.store = self._store_queryset.first()

        phone_variant = self.resolve_phone_variant_from_payload()
        product.phone_variant = phone_variant
        product.sync_phone_identity()
        if commit:
            product.save()
        if commit:
            self.save_product_attributes(product)
            self.sync_product_variants(product)
        return product

    def has_changed(self):
        if self.files:
            return True
        return super().has_changed()


# ─── Product Variant Form ─────────────────────────────────────────────────────

class ProductVariantForm(forms.ModelForm):
    amazon_seller_sku = forms.CharField(required=False, label="Amazon Seller SKU", max_length=120, widget=forms.TextInput(attrs={"placeholder": "Exact Amazon seller SKU"}))
    amazon_asin = forms.CharField(required=False, label="Amazon ASIN", max_length=20, widget=forms.TextInput(attrs={"placeholder": "Example: B0CVJ8716B"}))

    class Meta:
        model = ProductVariant
        fields = ["name", "sku", "barcode", "price", "discount_price", "is_default"]

    def __init__(self, *args, **kwargs):
        product = kwargs.pop("product", None)
        super().__init__(*args, **kwargs)
        if product is None and self.instance and self.instance.pk:
            # Read the foreign-key id first. Accessing instance.product can
            # raise RelatedObjectDoesNotExist when a stale/incomplete
            # instance reaches the form.
            product_id = getattr(self.instance, "product_id", None)
            product = Product.objects.filter(pk=product_id).first() if product_id else None
        if product is None:
            product = self.initial.get("product")
        if product and self.instance and self.instance.pk:
            connection = MarketplaceConnection.objects.filter(connector__code="amazon").first()
            listing = MarketplaceListing.objects.filter(
                connection=connection, product=product, variant=self.instance,
            ).order_by("-external_listing_id", "-updated_at").first() if connection else None
            if listing:
                self.initial["amazon_seller_sku"] = listing.seller_sku
                self.initial["amazon_asin"] = listing.external_listing_id

        # Add dynamic select fields for variant-eligible attributes (Color, Size, etc.)
        if product:
            from apps.catalog.models import ProductAttribute, ProductVariantAttributeValue
            # Get variant-eligible attributes
            attrs = ProductAttribute.objects.filter(is_variant_attribute=True)
            for attr in attrs:
                field_name = f"attrib_{attr.code}"
                choices = [("", f"Select {attr.name}")]
                for val in attr.values.all():
                    choices.append((val.value, val.label))
                
                initial_val = ""
                if self.instance and self.instance.pk:
                    val_obj = ProductVariantAttributeValue.objects.filter(variant=self.instance, attribute=attr).first()
                    if val_obj:
                        initial_val = val_obj.value
                
                self.fields[field_name] = forms.ChoiceField(
                    choices=choices,
                    required=False,
                    initial=initial_val,
                    label=attr.name
                )

        # Inject CSS classes dynamically
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                pass
            else:
                field.widget.attrs["class"] = "ra-input"

    def save(self, commit=True):
        variant = super().save(commit=commit)
        if commit:
            from apps.catalog.models import ProductAttribute, ProductVariantAttributeValue
            # Save the dynamic attribute mappings
            attrs = ProductAttribute.objects.filter(is_variant_attribute=True)
            for attr in attrs:
                field_name = f"attrib_{attr.code}"
                val_data = self.cleaned_data.get(field_name)
                if val_data:
                    ProductVariantAttributeValue.objects.update_or_create(
                        variant=variant,
                        attribute=attr,
                        defaults={"value": val_data}
                    )
                else:
                    ProductVariantAttributeValue.objects.filter(variant=variant, attribute=attr).delete()
        return variant
