from django.contrib import admin
from django import forms
from django.utils.safestring import mark_safe

from .forms import MultipleFileField, MultipleFileInput
from .models import (
    AttributeValue,
    Brand,
    Category,
    Product,
    ProductAttribute,
    ProductAttributeOption,
    ProductMedia,
    ProductVariant,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "sort_order", "is_featured", "is_active", "category_image_status")
    search_fields = ("name", "slug", "description")
    list_filter = ("is_featured", "is_active")
    readonly_fields = ("category_image_preview",)
    fieldsets = (
        (None, {"fields": ("name", "slug", "parent", "description")}),
        (
            "Homepage category card images",
            {
                "description": "Upload separate images for each device. Tablet and mobile fall back to the desktop image when left empty.",
                "fields": (
                    "category_image_desktop",
                    "category_image_tablet",
                    "category_image_mobile",
                    "category_image_alt",
                    "category_image_preview",
                ),
            },
        ),
        ("Visibility and ordering", {"fields": ("is_active", "is_featured", "sort_order")}),
        ("SEO", {"fields": ("seo_title", "seo_description")}),
    )

    @admin.display(description="Card image")
    def category_image_status(self, obj):
        return "Configured" if obj.category_image_desktop else "Product fallback"

    @admin.display(description="Current previews")
    def category_image_preview(self, obj):
        images = (
            ("Desktop", obj.category_image_desktop),
            ("Tablet", obj.category_image_tablet),
            ("Mobile", obj.category_image_mobile),
        )
        previews = []
        for label, image in images:
            if image:
                previews.append(
                    f'<div style="display:inline-flex;flex-direction:column;gap:6px;margin:0 14px 12px 0;vertical-align:top;">'
                    f'<strong>{label}</strong><img src="{image.url}" alt="{label} preview" style="width:150px;height:95px;object-fit:cover;border-radius:8px;border:1px solid #d9e1ea;">'
                    f'</div>'
                )
        return mark_safe("".join(previews) or "No category card images uploaded yet.")


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "website_url", "is_active")
    search_fields = ("name", "slug")


@admin.register(ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "data_type", "is_variant_attribute", "is_active")
    search_fields = ("name", "code")


class ProductAdminForm(forms.ModelForm):
    product_images = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={"multiple": True, "accept": "image/*"}),
        label="Product images",
    )
    product_videos = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={"multiple": True, "accept": "video/*"}),
        label="Product videos",
    )
    product_360_images = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={"multiple": True, "accept": "image/*"}),
        label="360 images",
    )
    product_video_urls = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "One video URL per line"}),
        label="External video URLs",
    )
    remove_asset_ids = forms.ModelMultipleChoiceField(
        queryset=ProductMedia.objects.none(),
        required=False,
        widget=forms.MultipleHiddenInput(),
        label="Remove existing assets",
    )

    class Meta:
        model = Product
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["remove_asset_ids"].queryset = self.instance.media_items.order_by("sort_order", "title")

    def has_changed(self):
        if self.files:
            return True
        return super().has_changed()

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    list_display = ("name", "store", "sku", "price", "status", "is_featured", "is_active")
    search_fields = ("name", "sku", "barcode")
    list_filter = ("status", "is_featured", "is_active")
    readonly_fields = ("asset_manager_panel",)

    fieldsets = (
        (
            "Product Details",
            {
                "fields": (
                    "retailer",
                    "store",
                    "category",
                    "brand",
                    "name",
                    "model_name",
                    "slug",
                    "product_type",
                    "sku",
                    "barcode",
                    "qr_code",
                    "short_description",
                    "description",
                )
            },
        ),
        (
            "Pricing and Shipping",
            {
                "fields": (
                    "price",
                    "discount_price",
                    "tax_rate",
                    "weight",
                    "length",
                    "width",
                    "height",
                    "warranty",
                )
            },
        ),
        (
            "Product Gallery and Media",
            {
                "fields": (
                    "product_images",
                    "product_videos",
                    "product_360_images",
                    "product_video_urls",
                    "asset_manager_panel",
                ),
                "description": "Upload multiple product images, videos, 360 frames, or add external video URLs.",
            },
        ),
        (
            "SEO and Status",
            {
                "fields": (
                    "seo_title",
                    "seo_description",
                    "seo_keywords",
                    "status",
                    "approved_at",
                    "approved_by",
                    "approval_notes",
                    "is_featured",
                    "is_active",
                )
            },
        ),
    )

    def asset_manager_panel(self, obj):
        if not obj or not obj.pk:
            return "Save this product first to manage current assets."

        cards = []
        for asset in obj.media_items.order_by("sort_order", "-is_primary", "created_at"):
            if asset.file:
                if asset.media_type in (ProductMedia.TYPE_IMAGE, ProductMedia.TYPE_IMAGE_360):
                    preview = (
                        f'<img src="{asset.file.url}" alt="{asset.title or "Asset"}" '
                        'class="asset-manager-preview">'
                    )
                else:
                    preview = '<div class="asset-manager-preview asset-manager-video">Video</div>'
            else:
                preview = '<div class="asset-manager-preview asset-manager-link">Link</div>'

            primary_control = ""
            if asset.media_type == ProductMedia.TYPE_IMAGE:
                checked = "checked" if asset.is_primary else ""
                primary_control = (
                    '<label class="asset-inline-field asset-inline-radio">'
                    f'<input type="radio" name="primary_asset_id" value="{asset.id}" {checked}>'
                    '<span>Front Display Image</span>'
                    '</label>'
                )

            cards.append(
                f'''
                <div class="asset-manager-card" data-asset-card="{asset.pk}">
                    <div class="asset-manager-head">
                        {preview}
                        <div class="asset-manager-meta">
                            <div class="asset-manager-name">{asset.title or asset.get_media_type_display()}</div>
                            <div class="asset-manager-copy">Lower sort order appears first. Toggle remove to mark for deletion.</div>
                        </div>
                        <button type="button" class="asset-remove-toggle" data-asset-remove-id="{asset.pk}">Remove</button>
                    </div>
                    <div class="asset-manager-controls">
                        <label class="asset-inline-field asset-inline-sort">
                            <span>Sort order</span>
                            <input type="number" name="asset_sort_{asset.id}" value="{asset.sort_order}" min="0">
                        </label>
                        {primary_control}
                    </div>
                </div>
                '''
            )

        return mark_safe(
            '<style>'
            '.asset-manager{display:grid;gap:14px}'
            '.asset-manager-card{display:grid;gap:14px;border:1px solid #e5e7eb;border-radius:12px;padding:14px;background:rgba(0,0,0,0.01)}'
            '.asset-manager-head{display:flex;align-items:center;gap:12px}'
            '.asset-manager-preview{width:64px;height:64px;object-fit:cover;border-radius:8px;border:1px solid #e5e7eb;background:#f8fafc;display:grid;place-items:center;flex:0 0 64px}'
            '.asset-manager-video,.asset-manager-link{background:#111827;color:#fff;font-size:12px;font-weight:700}'
            '.asset-manager-meta{flex:1}'
            '.asset-manager-name{font-weight:600;font-size:13.5px;color:#111827}'
            '.asset-manager-copy{font-size:11.5px;color:#6b7280}'
            '.asset-remove-toggle{margin-left:auto;padding:4px 10px;border:1px solid rgba(239,68,68,0.2);border-radius:8px;background:rgba(239,68,68,0.04);color:#dc2626;cursor:pointer}'
            '.asset-manager-controls{display:flex;align-items:center;justify-content:space-between;gap:16px;border-top:1px solid #e5e7eb;padding-top:12px}'
            '.asset-inline-field{display:flex;align-items:center;gap:8px}'
            '.asset-inline-field span{font-size:12px;font-weight:500;color:#111827}'
            '.asset-inline-sort input{width:72px;padding:4px 8px;border:1px solid #d1d5db;border-radius:6px}'
            '.asset-inline-radio{cursor:pointer}'
            '</style>'
            '<div id="admin-asset-manager" class="asset-manager">'
            + "".join(cards)
            + '</div><div id="admin-asset-remove-inputs"></div>'
            + """
            <script>
            (function() {
              const manager = document.getElementById('admin-asset-manager');
              const removeInputs = document.getElementById('admin-asset-remove-inputs');
              if (!manager || !removeInputs || manager.dataset.bound === '1') return;
              manager.dataset.bound = '1';
              manager.querySelectorAll('.asset-remove-toggle').forEach((button) => {
                button.addEventListener('click', () => {
                  const assetId = button.dataset.assetRemoveId;
                  const card = manager.querySelector(`[data-asset-card="${assetId}"]`);
                  if (!assetId || !card) return;
                  const existing = removeInputs.querySelector(`input[value="${assetId}"]`);
                  if (existing) {
                    existing.remove();
                    card.style.opacity = '1';
                    card.style.pointerEvents = 'auto';
                    button.textContent = 'Remove';
                    button.classList.remove('asset-remove-toggle--active');
                  } else {
                    const hidden = document.createElement('input');
                    hidden.type = 'hidden';
                    hidden.name = 'remove_asset_ids';
                    hidden.value = assetId;
                    removeInputs.appendChild(hidden);
                    card.style.opacity = '0.42';
                    card.style.pointerEvents = 'none';
                    button.textContent = 'Keep Asset';
                    button.classList.add('asset-remove-toggle--active');
                  }
                });
              });
            })();
            </script>
            """
        )
    asset_manager_panel.short_description = "Current Assets"

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        product = form.instance
        selected_remove_ids = set(request.POST.getlist("remove_asset_ids"))
        selected_primary_id = request.POST.get("primary_asset_id")

        for asset in product.media_items.all():
            sort_value = request.POST.get(f"asset_sort_{asset.id}")
            if sort_value not in (None, ""):
                try:
                    asset.sort_order = int(sort_value)
                except (TypeError, ValueError):
                    pass
            if asset.media_type == ProductMedia.TYPE_IMAGE:
                asset.is_primary = str(asset.id) == selected_primary_id if selected_primary_id else asset.is_primary
            asset.save(update_fields=["sort_order", "is_primary", "updated_at"])

        if selected_remove_ids:
            product.media_items.filter(id__in=selected_remove_ids).delete()

        if selected_primary_id and not product.media_items.filter(id=selected_primary_id, media_type=ProductMedia.TYPE_IMAGE).exists():
            fallback_primary = product.media_items.filter(media_type=ProductMedia.TYPE_IMAGE).order_by("sort_order", "created_at").first()
            if fallback_primary:
                product.media_items.filter(media_type=ProductMedia.TYPE_IMAGE).update(is_primary=False)
                fallback_primary.is_primary = True
                fallback_primary.save(update_fields=["is_primary", "updated_at"])

        next_sort_order = product.media_items.count()
        has_primary_image = product.media_items.filter(
            media_type=ProductMedia.TYPE_IMAGE,
            is_primary=True,
        ).exists()

        for image in request.FILES.getlist("product_images"):
            ProductMedia.objects.create(
                product=product,
                media_type=ProductMedia.TYPE_IMAGE,
                file=image,
                title=getattr(image, "name", ""),
                is_primary=not has_primary_image,
                sort_order=next_sort_order,
            )
            has_primary_image = True
            next_sort_order += 1

        for video in request.FILES.getlist("product_videos"):
            ProductMedia.objects.create(
                product=product,
                media_type=ProductMedia.TYPE_VIDEO,
                file=video,
                title=getattr(video, "name", ""),
                sort_order=next_sort_order,
            )
            next_sort_order += 1

        for spin_image in request.FILES.getlist("product_360_images"):
            ProductMedia.objects.create(
                product=product,
                media_type=ProductMedia.TYPE_IMAGE_360,
                file=spin_image,
                title=getattr(spin_image, "name", ""),
                sort_order=next_sort_order,
            )
            next_sort_order += 1

        for video_url in (form.cleaned_data.get("product_video_urls") or "").splitlines():
            video_url = video_url.strip()
            if not video_url:
                continue
            ProductMedia.objects.create(
                product=product,
                media_type=ProductMedia.TYPE_VIDEO,
                external_url=video_url,
                title="External video",
                sort_order=next_sort_order,
            )
            next_sort_order += 1


admin.site.register(ProductVariant)
