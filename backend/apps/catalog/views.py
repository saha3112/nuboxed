from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from collections import defaultdict
import json
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import CreateView, DetailView, TemplateView, UpdateView, View

from apps.backoffice.views import SuperAdminRequiredMixin
from apps.catalog.forms import ProductForm, ProductVariantForm
from apps.catalog.models import AttributeValue, Product, ProductMedia, ProductVariant
from apps.catalog.services import approve_product, normalize_comma_separated_phone_models, reject_product, unique_slug, unique_sku
from apps.inventory.delivery import estimate_product_delivery, get_request_location_payload, serialize_delivery_context
from apps.retailers.views import RetailerPortalMixin
from apps.stores.models import Store
from apps.users.models import User
from apps.settings_app.services import get_effective_sale_countdown


class ProductAssetSyncMixin:
    def get_external_video_rows_json(self, product=None):
        if not product or not getattr(product, "pk", None):
            return "[]"
        rows = [
            {
                "id": str(asset.id),
                "url": asset.external_url,
                "title": asset.title or "External video",
            }
            for asset in product.media_items.filter(
                media_type=ProductMedia.TYPE_VIDEO,
            ).exclude(external_url="").order_by("sort_order", "created_at")
        ]
        return json.dumps(rows)

    def get_phone_picker_context(self, product=None):
        from apps.catalog.models import PhoneBrand, PhoneColorOption, PhoneModel, PhoneModelVariant, PhonePlatform, PhoneStorageOption, PhoneRamOption

        normalize_comma_separated_phone_models()
        platforms = PhonePlatform.objects.all().order_by("name")
        brands = PhoneBrand.objects.select_related("platform").order_by("platform__name", "sort_order", "name")
        models = PhoneModel.objects.select_related("platform", "brand").filter(is_active=True).order_by("platform__name", "brand__name", "sort_order", "name")
        variants = PhoneModelVariant.objects.select_related("phone_model", "phone_model__brand").order_by("phone_model__name", "sort_order", "storage", "color")
        storages = PhoneStorageOption.objects.filter(is_active=True).order_by("sort_order", "label")
        colors = PhoneColorOption.objects.filter(is_active=True).order_by("sort_order", "name")
        rams = PhoneRamOption.objects.filter(is_active=True).order_by("sort_order", "label")
        return {
            "all_platforms": platforms,
            "all_phone_brands": brands,
            "all_phone_models": models,
            "all_phone_variants": variants,
            "phone_picker_payload": json.dumps(
                {
                    "platforms": [{"id": str(item.id), "name": item.name, "label": item.get_name_display()} for item in platforms],
                    "brands": [
                        {
                            "id": str(item.id),
                            "name": item.name,
                            "label": item.name,
                            "platform_id": str(item.platform_id),
                            "platform_name": item.platform.name,
                        }
                        for item in brands
                    ],
                    "models": [
                        {
                            "id": str(item.id),
                            "name": item.name,
                            "display_name": item.display_name,
                            "platform_id": str(item.platform_id),
                            "platform_name": item.platform.name,
                            "brand_id": str(item.brand_id) if item.brand_id else "",
                        }
                        for item in models
                    ],
                    "variants": [
                        {
                            "id": str(item.id),
                            "label": item.display_name,
                            "phone_model_id": str(item.phone_model_id),
                            "ram": item.ram,
                            "storage": item.storage,
                            "color": item.color,
                            "color_hex": item.color_hex,
                        }
                        for item in variants
                    ],
                    "storages": [{"id": item.label, "label": item.label} for item in storages],
                    "colors": [{"id": item.name, "label": item.name, "color_hex": item.color_hex} for item in colors],
                    "rams": [{"id": item.label, "label": item.label} for item in rams],
                }
            ),
            "selected_phone_variant": getattr(product, "phone_variant", None),
            "selected_phone_variant_id": str(product.phone_variant_id) if getattr(product, "phone_variant_id", None) else "",
        }

    def sync_product_assets(self, product, form):
        selected_remove_ids = set(self.request.POST.getlist("remove_asset_ids"))
        # featured_media_id can be any media type (image, video, 360)
        featured_media_id = self.request.POST.get("featured_media_id") or self.request.POST.get("primary_asset_id")

        if featured_media_id:
            # Clear is_primary across ALL media, then set selected one
            product.media_items.all().update(is_primary=False)

        for asset in product.media_items.all():
            sort_value = self.request.POST.get(f"asset_sort_{asset.id}")
            if sort_value not in (None, ""):
                try:
                    asset.sort_order = int(sort_value)
                except (TypeError, ValueError):
                    pass
            if featured_media_id:
                asset.is_primary = str(asset.id) == str(featured_media_id)
            color_value = self.request.POST.get(f"asset_color_{asset.id}", "").strip()
            asset.color = color_value or None
            asset.save(update_fields=["sort_order", "is_primary", "color", "updated_at"])

        if selected_remove_ids:
            product.media_items.filter(id__in=selected_remove_ids).delete()

        for asset in form.cleaned_data.get("remove_asset_ids", []):
            if asset.product_id == product.id:
                asset.delete()

        # Ensure at least one image is primary if none set
        if not product.media_items.filter(is_primary=True).exists():
            fallback = product.media_items.order_by("sort_order", "created_at").first()
            if fallback:
                fallback.is_primary = True
                fallback.save(update_fields=["is_primary", "updated_at"])

        existing_count = product.media_items.count()
        next_sort_order = existing_count
        has_primary_image = product.media_items.filter(
            media_type=ProductMedia.TYPE_IMAGE,
            is_primary=True,
        ).exists()

        # Handle uploaded image files
        for image in self.request.FILES.getlist("product_images"):
            ProductMedia.objects.create(
                product=product,
                media_type=ProductMedia.TYPE_IMAGE,
                file=image,
                is_primary=not has_primary_image,
                sort_order=next_sort_order,
                title=getattr(image, "name", ""),
            )
            has_primary_image = True
            next_sort_order += 1

        # Handle images selected from the media library
        lib_images_raw = self.request.POST.get("product_images_library_ids", "")
        if lib_images_raw:
            from .models import MediaLibrary
            for lib_id in lib_images_raw.split(","):
                if lib_id.strip():
                    try:
                        asset = MediaLibrary.objects.get(id=lib_id)
                        ProductMedia.objects.create(
                            product=product,
                            media_type=ProductMedia.TYPE_IMAGE,
                            file=asset.file,
                            is_primary=not has_primary_image,
                            sort_order=next_sort_order,
                            title=asset.filename,
                        )
                        has_primary_image = True
                        next_sort_order += 1
                    except Exception:
                        pass

        # Handle uploaded video files
        for video in self.request.FILES.getlist("product_videos"):
            ProductMedia.objects.create(
                product=product,
                media_type=ProductMedia.TYPE_VIDEO,
                file=video,
                sort_order=next_sort_order,
                title=getattr(video, "name", ""),
            )
            next_sort_order += 1

        # Handle videos selected from the media library
        lib_videos_raw = self.request.POST.get("product_videos_library_ids", "")
        if lib_videos_raw:
            from .models import MediaLibrary
            for lib_id in lib_videos_raw.split(","):
                if lib_id.strip():
                    try:
                        asset = MediaLibrary.objects.get(id=lib_id)
                        ProductMedia.objects.create(
                            product=product,
                            media_type=ProductMedia.TYPE_VIDEO,
                            file=asset.file,
                            sort_order=next_sort_order,
                            title=asset.filename,
                        )
                        next_sort_order += 1
                    except Exception:
                        pass

        # Handle uploaded 360 spin frames
        for spin_image in self.request.FILES.getlist("product_360_images"):
            ProductMedia.objects.create(
                product=product,
                media_type=ProductMedia.TYPE_IMAGE_360,
                file=spin_image,
                sort_order=next_sort_order,
                title=getattr(spin_image, "name", ""),
            )
            next_sort_order += 1

        # Handle 360 spin frames selected from the media library
        lib_spin_raw = self.request.POST.get("product_360_images_library_ids", "")
        if lib_spin_raw:
            from .models import MediaLibrary
            for lib_id in lib_spin_raw.split(","):
                if lib_id.strip():
                    try:
                        asset = MediaLibrary.objects.get(id=lib_id)
                        ProductMedia.objects.create(
                            product=product,
                            media_type=ProductMedia.TYPE_IMAGE_360,
                            file=asset.file,
                            sort_order=next_sort_order,
                            title=asset.filename,
                        )
                        next_sort_order += 1
                    except Exception:
                        pass

        # Synchronize external video URLs. Rows include asset IDs so edits update
        # existing media records instead of deleting/recreating them.
        current_ext_videos = product.media_items.filter(media_type=ProductMedia.TYPE_VIDEO).exclude(external_url="")
        existing_by_id = {str(v.id): v for v in current_ext_videos}
        submitted_rows = []

        # Support both dynamic list fields (video_url_list[]) and legacy textarea
        list_urls = self.request.POST.getlist("video_url_list[]")
        list_ids = self.request.POST.getlist("video_url_asset_id[]")
        if list_urls:
            for index, video_url in enumerate(list_urls):
                video_url = video_url.strip()
                if video_url:
                    submitted_rows.append({
                        "id": (list_ids[index] if index < len(list_ids) else "").strip(),
                        "url": video_url,
                    })
        else:
            for video_url in (form.cleaned_data.get("product_video_urls") or "").splitlines():
                video_url = video_url.strip()
                if video_url:
                    submitted_rows.append({"id": "", "url": video_url})

        kept_ids = set()
        seen_urls = set()
        for row in submitted_rows:
            url = row["url"]
            if url in seen_urls:
                continue
            seen_urls.add(url)
            asset = existing_by_id.get(row["id"])
            if asset:
                asset.external_url = url
                if not asset.title:
                    asset.title = "External video"
                asset.save(update_fields=["external_url", "title", "updated_at"])
                kept_ids.add(str(asset.id))
                continue

            asset = current_ext_videos.filter(external_url=url).first()
            if asset:
                kept_ids.add(str(asset.id))
                continue

            ProductMedia.objects.create(
                product=product,
                media_type=ProductMedia.TYPE_VIDEO,
                external_url=url,
                sort_order=next_sort_order,
                title="External video",
            )
            next_sort_order += 1

        current_ext_videos.exclude(id__in=kept_ids).delete()

    def sync_default_variant(self, product, form):
        if not product.pk:
            return
        selected_variant = form.cleaned_data.get("default_variant")
        if not selected_variant:
            return
        product.variants.update(is_default=False)
        product.variants.filter(id=selected_variant.id).update(is_default=True)


class RetailerCatalogDashboardView(RetailerPortalMixin, TemplateView):
    template_name = "catalog/retailer_products.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        retailer = self.get_retailer()
        queryset = Product.objects.filter(
            retailer=retailer,
            deleted_at__isnull=True,
        ).select_related("store", "category", "brand")
        context.update(
            {
                "page_title": "Catalog Products",
                "products": queryset.order_by("-created_at"),
            }
        )
        return context


class RetailerProductCreateView(ProductAssetSyncMixin, RetailerPortalMixin, CreateView):
    template_name = "catalog/product_form.html"
    form_class = ProductForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["store_queryset"] = self.get_store_queryset(self.get_retailer())
        kwargs["allow_sale_countdown"] = self.has_retailer_permission("sale_countdown.manage")
        kwargs["allow_sale_message"] = False
        return kwargs

    def form_valid(self, form):
        product = form.save(commit=False)
        product.retailer = self.get_retailer()
        product.slug = unique_slug(Product, product.name)
        product.sku = unique_sku(Product, product.name)
        product.status = Product.STATUS_APPROVED
        product.is_active = True
        product.save()
        self.object = product
        form.save_product_attributes(product)
        form.sync_product_variants(product)
        self.sync_product_assets(product, form)
        self.sync_default_variant(product, form)
        messages.success(self.request, "Product created and approved.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        if self.request.POST.get("save_action", "stay") == "exit":
            return reverse("catalog:retailer-products")
        return reverse("catalog:retailer-product-edit", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Create Product"
        context["external_video_rows_json"] = "[]"
        context.update(self.get_phone_picker_context())
        return context


class RetailerProductEditView(ProductAssetSyncMixin, RetailerPortalMixin, UpdateView):
    template_name = "catalog/product_form.html"
    form_class = ProductForm

    def get_queryset(self):
        retailer = self.get_retailer()
        return Product.objects.filter(retailer=retailer, deleted_at__isnull=True)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        store_queryset = self.get_store_queryset(self.get_retailer())
        if getattr(self.object, "store_id", None):
            store_queryset = Store.objects.filter(
                Q(id__in=store_queryset.values("id")) | Q(id=self.object.store_id)
            ).distinct()
        kwargs["store_queryset"] = store_queryset
        kwargs["allow_sale_countdown"] = self.has_retailer_permission("sale_countdown.manage")
        kwargs["allow_sale_message"] = False
        return kwargs

    def form_valid(self, form):
        product = form.save(commit=False)
        product.status = Product.STATUS_APPROVED
        product.is_active = True
        product.save()
        self.object = product
        form.save_product_attributes(product)
        form.sync_product_variants(product)
        self.sync_product_assets(product, form)
        self.sync_default_variant(product, form)
        messages.success(self.request, "Product updated.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        if self.request.POST.get("save_action", "stay") == "exit":
            return reverse("catalog:retailer-products")
        return reverse("catalog:retailer-product-edit", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()
        other_products = Product.objects.filter(
            retailer=self.get_retailer(),
            store=product.store,
            is_active=True
        ).exclude(id=product.id).order_by("name")
        context.update(
            {
                "page_title": "Edit Product",
                "product_variants": product.variants.all(),
                "product_assets": product.media_items.all().order_by("sort_order", "-is_primary"),
                "external_video_rows_json": self.get_external_video_rows_json(product),
                "other_products": other_products,
            }
        )
        context.update(self.get_phone_picker_context(product=product))
        return context


class RetailerProductVariantCreateView(RetailerPortalMixin, CreateView):
    template_name = "catalog/product_variant_form.html"
    form_class = ProductVariantForm

    def get_product(self):
        retailer = self.get_retailer()
        queryset = Product.objects.filter(retailer=retailer, deleted_at__isnull=True)
        return get_object_or_404(queryset, id=self.kwargs["product_id"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["initial"] = kwargs.get("initial", {})
        kwargs["initial"]["product"] = self.get_product()
        return kwargs

    def form_valid(self, form):
        variant = form.save(commit=False)
        variant.product = self.get_product()
        if not variant.sku:
            variant.sku = unique_sku(type(variant), f"{variant.product.name}-{variant.name}")
        if not variant.price:
            variant.price = variant.product.price
        if not variant.discount_price and variant.product.discount_price:
            variant.discount_price = variant.product.discount_price
        
        # Save to database first to get variant ID, then trigger form save with commit=True to save attributes
        variant.save()
        form.save(commit=True)
        
        messages.success(self.request, "Product variant added.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        next_url = self.request.GET.get("next")
        if next_url == "variants":
            return reverse("catalog:retailer-variants")
        return reverse("catalog:retailer-product-edit", kwargs={"pk": self.kwargs["product_id"]})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Add Product Variant"
        return context


class RetailerProductVariantEditView(RetailerPortalMixin, UpdateView):
    template_name = "catalog/product_variant_form.html"
    form_class = ProductVariantForm
    pk_url_kwarg = "variant_id"

    def get_queryset(self):
        retailer = self.get_retailer()
        return ProductVariant.objects.filter(
            product__retailer=retailer,
            product__deleted_at__isnull=True,
        ).select_related("product")

    def form_valid(self, form):
        variant = form.save()
        messages.success(self.request, "Product variant updated.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        next_url = self.request.GET.get("next")
        if next_url == "variants":
            return reverse("catalog:retailer-variants")
        return reverse("catalog:retailer-product-edit", kwargs={"pk": self.object.product_id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Product Variant"
        return context


class RetailerProductVariantListView(RetailerPortalMixin, TemplateView):
    template_name = "catalog/retailer_variants.html"

    def get(self, request, *args, **kwargs):
        return redirect("catalog:retailer-products")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        retailer = self.get_retailer()
        products = Product.objects.filter(
            retailer=retailer,
            deleted_at__isnull=True,
        ).order_by("name")
        variants = ProductVariant.objects.filter(
            product__retailer=retailer,
            product__deleted_at__isnull=True,
            deleted_at__isnull=True,
        ).select_related("product").order_by("product__name", "name")
            
        context.update({
            "page_title": "Device Models",
            "products": products,
            "variants": variants,
        })
        return context


class RetailerProductVariantDeleteView(RetailerPortalMixin, View):
    def post(self, request, *args, **kwargs):
        variant_id = self.kwargs.get("variant_id")
        retailer = self.get_retailer()
        queryset = ProductVariant.objects.filter(product__retailer=retailer, product__deleted_at__isnull=True)
            
        variant = get_object_or_404(queryset, id=variant_id)
        if variant.is_default:
            sibling = variant.product.variants.exclude(id=variant.id).first()
            if sibling:
                sibling.is_default = True
                sibling.save()
                
        product_name = variant.product.name
        variant_name = variant.name
        variant.delete()
        
        messages.success(request, f"Variant '{variant_name}' of product '{product_name}' was successfully deleted.")
        
        next_url = request.GET.get("next")
        if next_url == "variants":
            return redirect("catalog:retailer-variants")
        return redirect("catalog:retailer-product-edit", pk=variant.product_id)



class ProductDetailPageView(DetailView):
    template_name = "storefront/product_detail_page.html"
    model = Product
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return Product.objects.filter(status=Product.STATUS_APPROVED, is_active=True).select_related("category", "brand")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.object
        sorted_variants = self.get_stock_first_variants(product)
        req_variant_id = self.request.GET.get('variant')
        default_variant = None
        if req_variant_id:
            default_variant = next((v for v in sorted_variants if str(v.id) == req_variant_id), None)
            
        if not default_variant:
            default_variant = next((variant for variant in sorted_variants if variant.is_default and variant.available_qty > 0), None)
            default_variant = default_variant or next((variant for variant in sorted_variants if variant.available_qty > 0), None)
            default_variant = default_variant or (sorted_variants[0] if sorted_variants else None)
        product_family = self.resolve_product_family_value(product)
        related_products = self.get_related_products(product)
        similar_products = self.get_similar_products(product)
        stock_snapshot = self.get_stock_snapshot(product)
        location_payload = get_request_location_payload(self.request)
        delivery_estimate = estimate_product_delivery(product, location_payload=location_payload)
        delivery_window_label = self.get_delivery_window_label(delivery_estimate)
        similar_product_cards = []
        for similar_product in similar_products:
            similar_product_cards.append(
                {
                    "product": similar_product,
                    "delivery_estimate": estimate_product_delivery(
                        similar_product,
                        location_payload=location_payload,
                    ),
                }
            )

        # Build combined media list for gallery sorting
        media_list = []
        raw_media = product.media_items.exclude(media_type=ProductMedia.TYPE_IMAGE_360).order_by("sort_order", "-is_primary")
        for item in raw_media:
            media_list.append(item)
            
        spin_items = product.media_items.filter(media_type=ProductMedia.TYPE_IMAGE_360).order_by("sort_order")
        if spin_items.exists():
            first_360_order = spin_items.first().sort_order
            spin_entry = {
                "id": "360-view",
                "media_type": "image_360",
                "title": "360° View",
                "sort_order": first_360_order,
                "first_image_url": spin_items.first().file.url,
            }
            media_list.append(spin_entry)
            
        media_list.sort(key=lambda x: x["sort_order"] if isinstance(x, dict) else x.sort_order)

        variant_option_groups = []
        variant_attribute_map = defaultdict(list)
        variant_qs = sorted(
            product.variants.prefetch_related("attribute_values__attribute", "attribute_values__option"),
            key=self.get_variant_stock_sort_key,
        )
        for variant in variant_qs:
            attr_values = list(variant.attribute_values.all())
            if not attr_values:
                variant_attribute_map["Variant"].append(
                    {
                        "variant": variant,
                        "attribute": None,
                        "label": variant.name,
                        "value": variant.name,
                        "is_selected": default_variant and variant.id == default_variant.id,
                    }
                )
                continue

            for attr_value in attr_values:
                attr_key = attr_value.attribute.name if attr_value.attribute else "Variant"
                label = attr_value.option.value if attr_value.option_id and attr_value.option else (attr_value.value or variant.name)
                color_value = None
                color_swatch = None
                if attr_value.attribute and attr_value.attribute.is_color_type:
                    color_source = AttributeValue.objects.filter(
                        attribute=attr_value.attribute,
                    ).filter(
                        Q(value__iexact=attr_value.value) |
                        Q(label__iexact=label) |
                        Q(label__iexact=attr_value.value or "")
                    ).order_by("sort_order", "label").first()
                    if color_source:
                        color_value = color_source.hex_color or ""
                        if color_source.swatch:
                            color_swatch = color_source.swatch.url
                variant_attribute_map[attr_key].append(
                    {
                        "variant": variant,
                        "attribute": attr_value.attribute,
                        "label": label,
                        "value": attr_value.value or label,
                        "swatch_hex": color_value,
                        "swatch_image": color_swatch,
                        "is_color": bool(attr_value.attribute and attr_value.attribute.is_color_type),
                        "is_selected": default_variant and variant.id == default_variant.id,
                    }
                )

        for attr_name, items in variant_attribute_map.items():
            deduped = []
            seen = set()
            for item in items:
                key = item["label"].lower()
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(item)
            if "storage" in attr_name.lower() or "internal" in attr_name.lower() or "ram" in attr_name.lower() or "memory" in attr_name.lower():
                import re
                def parse_storage_size(item):
                    label = item["label"]
                    match = re.search(r'(\d+)\s*(GB|TB|MB)', label, re.IGNORECASE)
                    if match:
                        val = int(match.group(1))
                        unit = match.group(2).upper()
                        if unit == 'TB':
                            return val * 1024
                        if unit == 'MB':
                            return val / 1024
                        return val
                    return 0
                
                # Normalize labels for RAM and Storage to uppercase (e.g. '128 GB' -> '128GB')
                for item in deduped:
                    item["label"] = (item["label"] or "").replace(" ", "").upper()
                    item["value"] = (item["value"] or "").replace(" ", "").upper()
                
                deduped.sort(key=lambda item: (item["variant"].available_qty <= 0, parse_storage_size(item)))
            else:
                deduped.sort(key=lambda item: (item["variant"].available_qty <= 0, item["label"].lower()))
            variant_option_groups.append({"name": attr_name, "items": deduped})
        variant_option_groups.sort(key=lambda group: self.get_variant_group_order(group["name"]))

        context.update(
            {
                "page_title": product.seo_title or product.name,
                "media_list": media_list,
                "image_items": product.media_items.filter(media_type=ProductMedia.TYPE_IMAGE).order_by("sort_order", "-is_primary"),
                "video_items": product.media_items.filter(media_type=ProductMedia.TYPE_VIDEO).order_by("sort_order"),
                "spin_items": spin_items,
                "default_variant": default_variant,
                "variant_options": sorted_variants,
                "discount_percentage": self.get_discount_percentage(product),
                "stock_snapshot": stock_snapshot,
                "delivery_estimate": delivery_estimate,
                "delivery_window_label": delivery_window_label,
                "selected_delivery_location": serialize_delivery_context(location_payload),
                "product_family": product_family,
                "specifications": self.get_specifications(product, default_variant=default_variant),
                "related_products": related_products,
                "similar_products": similar_product_cards,
                "variant_option_groups": variant_option_groups,
                "display_price": (default_variant.discount_price or default_variant.price) if default_variant else (product.discount_price or product.price),
                "display_compare_price": default_variant.price if default_variant and default_variant.discount_price else (product.price if product.discount_price else None),
                "sale_countdown": get_effective_sale_countdown(product),
                "active_variant_name": default_variant.name if default_variant else None,
                "approved_reviews": product.reviews.filter(status="approved").order_by("-created_at"),
                "reviews_count": product.reviews.filter(status="approved").count(),
                "avg_rating": round(sum(r.rating for r in product.reviews.filter(status="approved")) / max(1, product.reviews.filter(status="approved").count()), 1),
            }
        )
        return context

    def get_stock_first_variants(self, product):
        variants = list(product.variants.prefetch_related("attribute_values__attribute", "attribute_values__option"))
        return sorted(variants, key=self.get_variant_stock_sort_key)

    def get_variant_stock_sort_key(self, variant):
        return (variant.available_qty <= 0, not variant.is_default, self.get_variant_storage_sort_value(variant), variant.name.lower())

    def get_variant_storage_sort_value(self, variant):
        import re
        storage_value = ""
        for attr_value in list(variant.attribute_values.all()):
            attr_name = attr_value.attribute.name if attr_value.attribute else ""
            if "storage" in attr_name.lower() or "internal" in attr_name.lower():
                option_value = attr_value.option.value if attr_value.option_id and attr_value.option else ""
                storage_value = attr_value.value or option_value
                break
        storage_value = storage_value or variant.name
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

    def get_delivery_window_label(self, delivery_estimate):
        if not delivery_estimate or not delivery_estimate.get("is_serviceable"):
            return delivery_estimate.get("date_label", "Unavailable") if delivery_estimate else "Unavailable"

        transit_days = delivery_estimate.get("delivery_days") or 0
        handling_days = delivery_estimate.get("handling_days") or 0
        if handling_days > 0:
            return f"{transit_days}-{transit_days + handling_days} Days"
        return f"{transit_days} Days"

    def resolve_product_family_value(self, product):
        if product.phone_variant and product.phone_variant.phone_model:
            return product.phone_variant.phone_model.display_name
        return product.model_name or product.barcode or product.qr_code or product.name

    def get_discount_percentage(self, product):
        if product.discount_price and product.price and product.price > 0:
            return int(((product.price - product.discount_price) / product.price) * 100)
        return 0

    def get_stock_snapshot(self, product):
        return product.storefront_stock_snapshot

    def get_variant_group_order(self, name):
        lowered = (name or "").lower()
        if "ram" in lowered or "memory" in lowered:
            return 0
        if "storage" in lowered or "internal" in lowered:
            return 1
        if "color" in lowered:
            return 2
        return 3

    def get_specifications(self, product, default_variant=None):
        model_value = product.phone_model_display_name if hasattr(product, "phone_model_display_name") else (product.model_name or product.name)
        return [
            ("Brand", product.brand.name if product.brand else "-"),
            ("Model", model_value or product.name),
            ("SKU", default_variant.sku if default_variant else product.sku),
            ("Barcode", product.barcode or "-"),
            ("Weight", product.weight),
            ("Dimensions", f"{product.length} x {product.width} x {product.height}"),
            ("Warranty", product.warranty or "-"),
            ("Tax", f"{product.tax_rate}%"),
        ]

    def get_related_products(self, product):
        qs = Product.objects.filter(
            status=Product.STATUS_APPROVED,
            is_active=True,
            retailer=product.retailer,
            store=product.store,
            category=product.category,
        ).exclude(id=product.id).prefetch_related("media_items")[:4]
        if not qs:
            qs = Product.objects.filter(
                status=Product.STATUS_APPROVED,
                is_active=True,
                retailer=product.retailer,
                store=product.store,
            ).exclude(id=product.id).prefetch_related("media_items").order_by("?")[:4]
        return qs

    def get_similar_products(self, product):
        family_key = product.phone_variant.phone_model.display_name if product.phone_variant and product.phone_variant.phone_model else product.model_name
        family_query = Q(name=product.name)
        if family_key:
            family_query = Q(model_name=family_key)
        elif product.barcode:
            family_query = Q(barcode=product.barcode)
        
        qs = Product.objects.filter(
            status=Product.STATUS_APPROVED,
            is_active=True,
            retailer=product.retailer,
            store=product.store,
        ).filter(family_query).exclude(id=product.id).select_related("store").prefetch_related("media_items")[:6]
        
        if not qs:
            qs = Product.objects.filter(
                status=Product.STATUS_APPROVED,
                is_active=True,
                retailer=product.retailer,
                store=product.store,
            ).exclude(id=product.id).select_related("store").prefetch_related("media_items").order_by("?")[:3]
        return qs

class AdminProductApproveActionView(SuperAdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        product = get_object_or_404(Product, id=self.kwargs["pk"])
        if self.kwargs["action"] == "approve":
            approve_product(product, approver=request.user, notes="Approved from Super Admin panel")
            messages.success(request, "Product approved successfully.")
        elif self.kwargs["action"] == "reject":
            reject_product(product, approver=request.user, notes="Rejected from Super Admin panel")
            messages.success(request, "Product rejected successfully.")
        else:
            raise Http404("Invalid action.")
        return redirect("backoffice:module-list", module="products")

class PortalMediaLibraryMixin:
    def get_media_user(self):
        portal_context = self.request.headers.get("X-Portal-Context", "")
        session_keys = []
        if portal_context == "retailer":
            session_keys = ["retailer_user_id", "backoffice_user_id"]
        elif portal_context == "backoffice":
            session_keys = ["backoffice_user_id", "retailer_user_id"]
        else:
            session_keys = ["retailer_user_id", "backoffice_user_id"]

        for session_key in session_keys:
            user_id = self.request.session.get(session_key)
            if user_id:
                user = User.objects.filter(pk=user_id, is_active=True).first()
                if user:
                    return user
                self.request.session.pop(session_key, None)

        if self.request.user.is_authenticated:
            return self.request.user
        return None

    def dispatch(self, request, *args, **kwargs):
        self.media_user = self.get_media_user()
        if not self.media_user:
            return JsonResponse({"status": "error", "message": "Authentication required"}, status=403)
        request.user = self.media_user
        return super().dispatch(request, *args, **kwargs)


class MediaLibraryListView(PortalMediaLibraryMixin, View):
    def get(self, request, *args, **kwargs):
        from .models import MediaLibrary
        assets = MediaLibrary.objects.filter(user=self.media_user).order_by("-created_at")
        data = []
        for asset in assets:
            # Get size in human-readable format
            size_kb = f"{asset.file_size / 1024:.1f} KB" if asset.file_size else "0 KB"
            data.append({
                "id": str(asset.id),
                "url": asset.file.url,
                "filename": asset.filename,
                "file_size_display": size_kb,
                "created_at": asset.created_at.strftime("%Y-%m-%d %H:%M"),
            })
        return JsonResponse({"status": "success", "data": data})


@method_decorator(csrf_exempt, name='dispatch')
class MediaLibraryUploadView(PortalMediaLibraryMixin, View):
    def post(self, request, *args, **kwargs):
        from .models import MediaLibrary
        file = request.FILES.get("file")
        if not file:
            return JsonResponse({"status": "error", "message": "No file uploaded"}, status=400)
        
        asset = MediaLibrary.objects.create(
            user=self.media_user,
            file=file
        )
        size_kb = f"{asset.file_size / 1024:.1f} KB" if asset.file_size else "0 KB"
        return JsonResponse({
            "status": "success",
            "data": {
                "id": str(asset.id),
                "url": asset.file.url,
                "filename": asset.filename,
                "file_size_display": size_kb,
                "created_at": asset.created_at.strftime("%Y-%m-%d %H:%M"),
            }
        })


import json
import itertools
from django.utils.text import slugify

@method_decorator(csrf_exempt, name='dispatch')
class RetailerProductVariantGenerateView(RetailerPortalMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            product = Product.objects.get(id=self.kwargs["product_id"], retailer=self.get_retailer())
        except Product.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Product not found"}, status=404)
        
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)
        
        attributes_data = body.get("attributes", [])
        if not attributes_data:
            return JsonResponse({"status": "error", "message": "No attributes provided"}, status=400)
        
        from apps.catalog.models import ProductAttribute, AttributeValue, ProductVariantAttributeValue
        
        attr_objects = []
        attr_values_lists = []
        
        for attr_item in attributes_data:
            attr_name = attr_item.get("name", "").strip()
            val_strings = [v.strip() for v in attr_item.get("values", []) if v.strip()]
            if not attr_name or not val_strings:
                continue
            
            code = slugify(attr_name)
            data_type = ProductAttribute.TYPE_COLOR if attr_name.lower() == "color" else ProductAttribute.TYPE_SELECT
            
            attr_obj, created = ProductAttribute.objects.get_or_create(
                code=code,
                defaults={
                    "name": attr_name,
                    "data_type": data_type,
                    "is_variant_attribute": True
                }
            )
            
            val_objs = []
            for val_str in val_strings:
                val_obj, _ = AttributeValue.objects.get_or_create(
                    attribute=attr_obj,
                    value=val_str.lower(),
                    defaults={"label": val_str, "value": val_str.lower()}
                )
                val_objs.append((attr_obj, val_obj))
            
            attr_objects.append(attr_obj)
            attr_values_lists.append(val_objs)
            
        if not attr_values_lists:
            return JsonResponse({"status": "error", "message": "No valid combinations can be made"}, status=400)
            
        combinations = list(itertools.product(*attr_values_lists))
        
        created_count = 0
        skipped_count = 0
        
        for comb in combinations:
            comb_sorted = sorted(comb, key=lambda x: x[0].name)
            variant_name = " / ".join([item[1].label for item in comb_sorted])
            
            existing_variants = product.variants.filter(name=variant_name)
            if existing_variants.exists():
                skipped_count += 1
                continue
            
            variant_sku = unique_sku(ProductVariant, f"{product.name}-{variant_name}")
            
            variant = ProductVariant.objects.create(
                product=product,
                name=variant_name,
                sku=variant_sku,
                price=product.price,
                discount_price=product.discount_price,
                is_default=not product.variants.exists()
            )
            
            for attr_obj, val_obj in comb:
                ProductVariantAttributeValue.objects.create(
                    variant=variant,
                    attribute=attr_obj,
                    value=val_obj.label
                )
            
            created_count += 1
            
        return JsonResponse({
            "status": "success",
            "message": f"Successfully generated {created_count} variants ({skipped_count} skipped)."
        })


@method_decorator(csrf_exempt, name='dispatch')
class RetailerProductMergeView(RetailerPortalMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            product = Product.objects.get(id=self.kwargs["product_id"], retailer=self.get_retailer())
        except Product.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Current product not found"}, status=404)
            
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)
            
        other_product_id = body.get("other_product_id")
        variant_name = body.get("variant_name", "").strip()
        attributes_data = body.get("attributes", {})
        
        if not other_product_id or not variant_name:
            return JsonResponse({"status": "error", "message": "Missing other_product_id or variant_name"}, status=400)
            
        try:
            other_product = Product.objects.get(id=other_product_id, retailer=self.get_retailer())
        except Product.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Target product to merge not found"}, status=404)
            
        if other_product.id == product.id:
            return JsonResponse({"status": "error", "message": "Cannot merge a product into itself"}, status=400)
            
        from apps.catalog.models import ProductAttribute, AttributeValue, ProductVariantAttributeValue, ProductMedia
        from apps.inventory.models import StockItem
        
        new_sku = unique_sku(ProductVariant, other_product.sku or f"{product.name}-{variant_name}")
        
        variant = ProductVariant.objects.create(
            product=product,
            name=variant_name,
            sku=new_sku,
            price=other_product.price or product.price,
            discount_price=other_product.discount_price or product.discount_price,
            is_default=not product.variants.exists()
        )
        
        for attr_code, val_label in attributes_data.items():
            if not val_label.strip():
                continue
            attr_obj, _ = ProductAttribute.objects.get_or_create(
                code=attr_code,
                defaults={"name": attr_code.title(), "is_variant_attribute": True}
            )
            ProductVariantAttributeValue.objects.update_or_create(
                variant=variant,
                attribute=attr_obj,
                defaults={"value": val_label}
            )
            
        for media in other_product.media_items.all():
            media.product = product
            media.variant = variant
            media.save()
            
        for stock in other_product.stock_items.all():
            existing_stock = StockItem.objects.filter(
                product=product,
                variant=variant,
                warehouse=stock.warehouse
            ).first()
            
            if existing_stock:
                existing_stock.on_hand_quantity += stock.on_hand_quantity
                existing_stock.reserved_quantity += stock.reserved_quantity
                existing_stock.damaged_quantity += stock.damaged_quantity
                existing_stock.returned_quantity += stock.returned_quantity
                existing_stock.save()
                stock.delete()
            else:
                stock.product = product
                stock.variant = variant
                stock.save()
                
        other_product.is_active = False
        if other_product.sku:
            other_product.sku = f"{other_product.sku}-merged-{variant.id}"
        other_product.save()
        
        return JsonResponse({
            "status": "success",
            "message": f"Successfully merged product '{other_product.name}' as variant '{variant_name}'."
        })


class ProductReviewSubmitView(View):
    def post(self, request, *args, **kwargs):
        from apps.catalog.models import ProductReview
        product_id = self.kwargs.get("product_id")
        product = get_object_or_404(Product, id=product_id)
        title = request.POST.get("title")
        reviewer_name = request.POST.get("name")
        comment = request.POST.get("review")
        rating = request.POST.get("rating", 5)

        try:
            rating = int(rating)
        except (ValueError, TypeError):
            rating = 5

        ProductReview.objects.create(
            product=product,
            title=title,
            reviewer_name=reviewer_name,
            comment=comment,
            rating=rating,
            status=ProductReview.STATUS_PENDING
        )

        return JsonResponse({
            "status": "success",
            "message": "Review submitted successfully and is pending approval."
        })


class RetailerProductReviewListView(RetailerPortalMixin, TemplateView):
    template_name = "catalog/retailer_reviews.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        retailer = self.get_retailer()

        # Check permissions
        if not retailer.can_approve_reviews:
            raise Http404("You do not have permission to manage reviews.")

        # Get all reviews for the retailer's products
        reviews = ProductReview.objects.filter(
            product__retailer=retailer,
            product__deleted_at__isnull=True
        ).select_related("product").order_by("-created_at")

        context.update({
            "page_title": "Product Reviews",
            "reviews": reviews,
        })
        return context


class RetailerProductReviewStatusView(RetailerPortalMixin, View):
    def post(self, request, pk, action, *args, **kwargs):
        retailer = self.get_retailer()

        # Check permissions
        if not retailer.can_approve_reviews:
            return JsonResponse({"status": "error", "message": "Permission denied"}, status=403)

        review = get_object_or_404(ProductReview, id=pk, product__retailer=retailer)

        if action == "approve":
            review.status = ProductReview.STATUS_APPROVED
            review.save()
            messages.success(request, f"Review for '{review.product.name}' has been approved.")
        elif action == "reject":
            review.status = ProductReview.STATUS_REJECTED
            review.save()
            messages.success(request, f"Review for '{review.product.name}' has been rejected.")
        elif action == "delete":
            review.delete()
            messages.success(request, "Review has been deleted.")
        else:
            return JsonResponse({"status": "error", "message": "Invalid action"}, status=400)

        return redirect("catalog:retailer-reviews")
