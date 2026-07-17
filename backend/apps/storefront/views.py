from collections import defaultdict
from decimal import Decimal, InvalidOperation
from urllib.parse import quote_plus

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db.models import Avg, Count, F, Max, Min, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.text import slugify
from django.views import View
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.core.paginator import Paginator

from apps.catalog.models import Category, Product, ProductMedia, Brand, AttributeValue
from apps.cms.models import FeaturedBanner, Slider
from apps.inventory.delivery import (
    clear_request_location,
    estimate_product_delivery,
    get_request_location_payload,
    resolve_geolocation_label,
    serialize_delivery_context,
    set_request_location,
)
from apps.orders.forms import CheckoutSelectionForm, UserAddressForm, build_payment_method_choices
from apps.orders.models import Order
from apps.orders.services import (
    add_product_to_cart,
    cart_delivery_payload,
    confirm_order,
    create_orders_from_cart,
    ensure_request_cart,
    recalculate_cart,
    resolve_checkout_address,
    sync_session_cart_to_db,
    update_cart_item_quantity,
)
from apps.retailers.models import Retailer
from apps.stores.models import Store, StoreRating
from apps.settings_app.models import StorefrontLocationMessages


def cart_session_key(product, variant=None):
    if variant is not None:
        return f"{product.id}:{variant.id}"
    return str(product.id)


APPROVED_PRODUCT_QS = Product.objects.filter(
    status=Product.STATUS_APPROVED,
    is_active=True,
    store__status=Store.STATUS_ACTIVE,
    store__is_active=True,
).select_related("category", "brand", "store", "retailer")


class StorefrontBaseMixin:
    def prioritize_available_products(self, products, *ordering):
        """Keep products with positive available stock ahead of unavailable products."""
        products = products.annotate(
            _stock_on_hand=Coalesce(Sum("stock_items__on_hand_quantity"), Value(0)),
            _stock_reserved=Coalesce(Sum("stock_items__reserved_quantity"), Value(0)),
        ).annotate(_available_stock=F("_stock_on_hand") - F("_stock_reserved"))
        return products.order_by("-_available_stock", *(ordering or ("-created_at",)))

    def normalize_query_value(self, value, default=""):
        if value is None:
            return default
        value = str(value).strip()
        if value.lower() in {"none", "null", "undefined"}:
            return default
        return value

    def parse_decimal_query_value(self, value):
        value = self.normalize_query_value(value, default="")
        if not value:
            return None
        try:
            return Decimal(value)
        except (InvalidOperation, TypeError, ValueError):
            return None

    def get_available_categories(self, products, selected_ids=None):
        category_ids = set(products.values_list("category_id", flat=True).distinct())
        if selected_ids:
            category_ids.update(int(value) for value in selected_ids if str(value).strip().isdigit())
        return Category.objects.filter(is_active=True, id__in=category_ids).order_by("sort_order", "name")

    def get_available_brands(self, products, selected_ids=None):
        brand_ids = set(products.exclude(brand_id__isnull=True).values_list("brand_id", flat=True).distinct())
        if selected_ids:
            brand_ids.update(int(value) for value in selected_ids if str(value).strip().isdigit())
        return Brand.objects.filter(id__in=brand_ids).order_by("name")

    def get_available_colors(self, products, selected_ids=None):
        color_ids = set(products.filter(variants__attribute_values__attribute__code="color").values_list(
            "variants__attribute_values__option_id",
            flat=True,
        ).distinct())
        if selected_ids:
            color_ids.update(int(value) for value in selected_ids if str(value).strip().isdigit())
        return AttributeValue.objects.filter(attribute__code="color", id__in=color_ids).order_by("sort_order", "label")

    def resolve_product_family_value(self, product):
        return product.model_name or product.barcode or product.qr_code or product.name

    def apply_stock_filter(self, products, in_stock_only=False):
        if in_stock_only:
            return products.filter(stock_items__on_hand_quantity__gt=0).distinct()
        return products

    def get_stock_snapshot(self, product):
        return product.storefront_stock_snapshot

    def get_discount_percentage(self, product):
        if product.discount_price and product.price and product.price > 0:
            delta = Decimal(product.price) - Decimal(product.discount_price)
            if delta > 0:
                return int((delta / Decimal(product.price)) * 100)
        return 0

    def get_delivery_payload(self):
        return get_request_location_payload(self.request)

    def get_store_proximity_score(self, store, payload=None):
        payload = payload or self.get_delivery_payload()
        pincode = self.normalize_query_value(payload.get("pincode"), default="").upper()
        country_code = self.normalize_query_value(payload.get("country_code"), default="").upper()
        city = self.normalize_query_value(payload.get("city"), default="").lower()

        store_postal = self.normalize_query_value(getattr(store, "postal_code", ""), default="").upper()
        store_city = self.normalize_query_value(getattr(store, "city", ""), default="").lower()
        store_country = self.normalize_query_value(getattr(store, "country_code", ""), default="").upper()

        score = 100
        if pincode and store_postal:
            if store_postal == pincode:
                score = 0
            elif pincode.startswith(store_postal[:min(len(store_postal), len(pincode))]):
                score = 1
            elif store_postal.startswith(pincode[:min(len(store_postal), len(pincode))]):
                score = 2
            elif pincode.isdigit() and store_postal.isdigit():
                score = 10 + min(abs(int(pincode) - int(store_postal)), 999999)
        if city and store_city and city == store_city:
            score = min(score, 3)
        if not pincode and country_code and store_country and country_code == store_country:
            score = min(score, 4)
        return score

    def order_stores_by_location(self, stores, payload=None):
        payload = payload or self.get_delivery_payload()
        items = list(stores)
        return sorted(
            items,
            key=lambda store: (
                self.get_store_proximity_score(store, payload=payload),
                self.normalize_query_value(getattr(store, "name", ""), default="").lower(),
            ),
        )

    def get_delivery_estimate(self, product, location_payload=None):
        return estimate_product_delivery(product, location_payload=location_payload or self.get_delivery_payload())

    def get_specifications(self, product, default_variant=None):
        variant_value = lambda field, fallback="": getattr(default_variant, field, fallback) if default_variant else fallback
        specs = [
            ("Brand", product.brand.name if product.brand else "-"),
            ("Model", product.model_name or product.name),
            ("SKU", default_variant.sku if default_variant else product.sku),
            ("Barcode", default_variant.barcode if default_variant and default_variant.barcode else product.barcode or "-"),
            ("Weight", variant_value("weight", product.weight)),
            ("Dimensions", f"{variant_value('length', product.length)} x {variant_value('width', product.width)} x {variant_value('height', product.height)}"),
            ("Warranty", variant_value("warranty", product.warranty) or "-"),
            ("Tax", f"{variant_value('tax_rate', product.tax_rate)}%"),
        ]
        return specs


    def apply_location_filter(self, queryset, location_payload, ignore_location=False, is_store_qs=False):
        if not location_payload or not (location_payload.get("pincode") or location_payload.get("city")):
            return queryset, "", ""
        if ignore_location:
            return queryset, "", ""
            
        if is_store_qs:
            stores = queryset.filter(status=Store.STATUS_ACTIVE, is_active=True)
        else:
            stores = Store.objects.filter(
                id__in=queryset.values("store_id"),
                status=Store.STATUS_ACTIVE,
                is_active=True,
            )
        ordered_stores = self.order_stores_by_location(stores, payload=location_payload)
        # Keep stores with score <= 3 (same city or pincode prefix)
        nearby_store_ids = [s.id for s in ordered_stores if self.get_store_proximity_score(s, payload=location_payload) <= 3]
        if not nearby_store_ids and ordered_stores:
            nearest_score = self.get_store_proximity_score(ordered_stores[0], payload=location_payload)
            nearby_store_ids = [
                store.id for store in ordered_stores
                if self.get_store_proximity_score(store, payload=location_payload) == nearest_score
            ][:3]
        
        # We always return the message if we are restricting
        if is_store_qs:
            location_messages = StorefrontLocationMessages.objects.filter(is_active=True).first()
            msg = (
                location_messages.other_location_message
                if location_messages and location_messages.other_location_message
                else "Do you want to see stores from stores in another location?"
            )
        else:
            msg = "Do you want to see products from stores in another location?"
        query_params = self.request.GET.copy()
        query_params["ignore_location"] = "1"
        url = "?" + query_params.urlencode()

        if is_store_qs:
            filtered_qs = queryset.filter(id__in=nearby_store_ids)
        else:
            filtered_qs = queryset.filter(store_id__in=nearby_store_ids)
            
        return filtered_qs, msg, url

    def get_featured_products(self, limit=8, location_payload=None, ignore_location=False):
        qs = APPROVED_PRODUCT_QS.filter(is_featured=True).prefetch_related(
            Prefetch("media_items", queryset=ProductMedia.objects.filter(media_type=ProductMedia.TYPE_IMAGE).order_by("sort_order"))
        )
        qs, _, _ = self.apply_location_filter(qs, location_payload, ignore_location=ignore_location)
        return qs[:limit]

    def get_category_sections(self, limit=4, items_per_category=8, location_payload=None, ignore_location=False):
        sections = []
        categories = Category.objects.filter(is_active=True).order_by("sort_order", "name")[:limit]
        for category in categories:
            products = APPROVED_PRODUCT_QS.filter(category=category)
            products, _, _ = self.apply_location_filter(products, location_payload, ignore_location=ignore_location)
            products = products[:items_per_category]
            if products:
                sections.append({"category": category, "products": products})
        return sections

    def get_cart_items(self, request):
        cart = ensure_request_cart(request)
        location_payload = cart_delivery_payload(request, cart)
        recalculate_cart(cart, location_payload=location_payload)
        return list(
            cart.items.select_related("product", "variant", "product__store").order_by("created_at")
        )

    def get_cart_totals(self, request):
        items = self.get_cart_items(request)
        cart = ensure_request_cart(request)
        return {
            "cart": cart,
            "items": items,
            "subtotal": cart.subtotal_amount,
            "discount": cart.discount_amount,
            "tax": cart.tax_amount,
            "shipping": cart.shipping_amount,
            "total": cart.total_amount,
            "coupon_code": cart.coupon_code,
        }

    def with_delivery_context(self, context):
        payload = self.get_delivery_payload()
        context["selected_delivery_location"] = serialize_delivery_context(payload)
        return context


class HomePageView(StorefrontBaseMixin, TemplateView):
    template_name = "storefront/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        location_payload = self.get_delivery_payload()
        ignore_location = self.request.GET.get("ignore_location") == "1"
        
        active_stores = Store.objects.filter(status=Store.STATUS_ACTIVE, is_active=True).order_by("name")
        active_stores, location_msg, location_url = self.apply_location_filter(active_stores, location_payload, ignore_location=ignore_location, is_store_qs=True)
        
        context.update(
            {
                "page_title": "CommerceOS Marketplace",
                "sliders": Slider.objects.exclude(status="draft").filter(is_active=True).order_by("sort_order")[:6],
                "featured_banners": FeaturedBanner.objects.exclude(status="draft").filter(is_active=True, placement="homepage")[:4],
                "featured_categories": Category.objects.filter(is_featured=True, is_active=True).order_by("sort_order", "name")[:8],
                "featured_products": self.get_featured_products(limit=8, location_payload=location_payload, ignore_location=ignore_location),
                "category_sections": self.get_category_sections(location_payload=location_payload, ignore_location=ignore_location),
                "active_stores": active_stores[:8],
                "location_msg": location_msg,
                "location_url": location_url,
            }
        )
        return self.with_delivery_context(context)


class StoreListingPageView(StorefrontBaseMixin, TemplateView):
    template_name = "storefront/store_listing.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        location_payload = self.get_delivery_payload()
        stores = Store.objects.filter(status=Store.STATUS_ACTIVE, is_active=True).select_related("retailer")
        if query:
            stores = stores.filter(
                Q(name__icontains=query)
                | Q(description__icontains=query)
                | Q(city__icontains=query)
                | Q(state__icontains=query)
                | Q(postal_code__icontains=query)
                | Q(country_code__icontains=query)
            )
        ignore_location = self.request.GET.get("ignore_location") == "1"
        stores, other_location_msg, other_location_url = self.apply_location_filter(
            stores, location_payload, ignore_location=ignore_location, is_store_qs=True
        )
        ordered_stores = self.order_stores_by_location(stores, payload=location_payload)
        context.update(
            {
                "page_title": "Stores",
                "stores": ordered_stores,
                "search_query": query,
                "selected_delivery_location": location_payload,
                "other_location_msg": other_location_msg,
                "other_location_url": other_location_url,
            }
        )
        return self.with_delivery_context(context)


class RetailerStorePageView(StorefrontBaseMixin, TemplateView):
    template_name = "storefront/store_detail.html"

    def _image_object_fit(self, value):
        fit = (value or "cover").strip().lower()
        if fit in {"contain", "cover", "fill", "none", "scale-down"}:
            return fit
        if fit in {"auto", "actual"}:
            return "contain"
        if fit in {"100% 100%", "stretch"}:
            return "fill"
        return "cover"

    def _build_store_category_tree(self, products):
        def brands_for(product_queryset):
            return list(
                product_queryset.filter(brand__isnull=False)
                .values("brand__id", "brand__name", "brand__slug")
                .annotate(product_count=Count("id", distinct=True))
                .order_by("brand__name")
            )

        def brand_tabs_for(product_queryset, category_slug):
            tabs = []
            for brand in brands_for(product_queryset):
                brand_products = product_queryset.filter(brand__slug=brand["brand__slug"])
                models = []
                for model_name in brand_products.values_list("model_name", flat=True).distinct().order_by("model_name"):
                    if not model_name:
                        continue
                    models.append({
                        "name": model_name,
                        "id": f"store-model-{category_slug}-{brand['brand__slug']}-{slugify(model_name)}",
                        "products": brand_products.filter(model_name=model_name),
                    })
                tabs.append({
                    "name": brand["brand__name"],
                    "id": f"store-brand-{category_slug}-{brand['brand__slug']}",
                    "products": brand_products,
                    "models": models,
                })
            return tabs

        product_categories = list(
            Category.objects.filter(products__in=products)
            .select_related("parent")
            .distinct()
            .order_by("parent__sort_order", "parent__name", "sort_order", "name")
        )
        grouped = {}
        for category in product_categories:
            parent = category.parent or category
            parent_key = str(parent.id)
            parent_entry = grouped.setdefault(
                parent_key,
                {
                    "category": parent,
                    "id": f"category-{parent.slug}",
                    "count": 0,
                    "products": products.filter(category=parent) if category.parent else products.filter(category=category),
                    "children": [],
                    "brands": [],
                },
            )
            if category.parent:
                child_products = products.filter(category=category)
                child_count = child_products.count()
                if child_count:
                    parent_entry["children"].append(
                        {
                            "category": category,
                            "id": f"category-{category.slug}",
                            "count": child_count,
                            "products": child_products,
                            "brands": brands_for(child_products),
                            "brand_tabs": brand_tabs_for(child_products, category.slug),
                        }
                    )
                    parent_entry["count"] += child_count
            else:
                parent_entry["count"] += parent_entry["products"].count()
        for entry in grouped.values():
            if not entry["children"]:
                entry["brands"] = brands_for(entry["products"])
        return [entry for entry in grouped.values() if entry["count"] or entry["products"].exists()]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        store = get_object_or_404(Store.objects.select_related("retailer"), slug=self.kwargs["slug"], status=Store.STATUS_ACTIVE, is_active=True)
        # Older data can contain more than one store for a retailer. If the
        # public active store is missing location fields, use the populated
        # sibling record so retailer/admin edits remain visible consistently.
        location_fields = ("address_line1", "address_line2", "city", "state", "postal_code", "country_code")
        sibling = (
            Store.objects.filter(retailer_id=store.retailer_id)
            .exclude(pk=store.pk)
            .order_by("-updated_at", "-created_at")
            .first()
        )
        if sibling:
            for field_name in location_fields:
                if not getattr(store, field_name, "") and getattr(sibling, field_name, ""):
                    setattr(store, field_name, getattr(sibling, field_name))
        products = self.prioritize_available_products(
            APPROVED_PRODUCT_QS.filter(store=store).prefetch_related(
                "media_items", "variants__attribute_values__attribute", "variants__attribute_values__option"
            )
        )
        category_groups = self._build_store_category_tree(products)
        categories = category_groups
        store_brands = list(
            products.filter(brand__isnull=False)
            .values("brand__name", "brand__slug")
            .annotate(product_count=Count("id", distinct=True))
            .order_by("brand__name")
        )
        store_page_sections = []
        for section in store.store_page_sections or []:
            if not isinstance(section, dict):
                continue
            if section.get("deleted_at"):
                continue
            enriched = dict(section)
            enriched["image_object_fit"] = self._image_object_fit(section.get("image_fit"))
            if isinstance(enriched.get("tiles"), list):
                enriched["tiles"] = [
                    {**tile, "image_object_fit": self._image_object_fit(tile.get("image_fit"))}
                    for tile in enriched["tiles"]
                    if isinstance(tile, dict)
                ]
            if section.get("type") == "category_feature" and section.get("category_slug"):
                category = Category.objects.filter(slug=section["category_slug"]).first()
                if category:
                    enriched["category"] = category
                    enriched["products"] = products.filter(category=category)[:4]
            elif section.get("type") == "product_shelf":
                slugs = [slug.strip() for slug in (section.get("product_slugs") or "").split(",") if slug.strip()]
                if slugs:
                    shelf_products = list(products.filter(slug__in=slugs))
                    shelf_products.sort(key=lambda product: slugs.index(product.slug) if product.slug in slugs else 999)
                    enriched["products"] = shelf_products[:8]
                else:
                    enriched["products"] = products[:8]
            store_page_sections.append(enriched)
        context.update(
            {
                "page_title": store.name,
                "store": store,
                "products": products,
                "store_categories": categories,
                "store_brands": store_brands,
                "store_category_groups": category_groups,
                "store_page_sections": store_page_sections,
                "store_rating_count": store.ratings.filter(is_approved=True, is_active=True).count(),
                "store_map_query": ", ".join(
                    value for value in [
                        store.address_line1,
                        store.address_line2,
                        store.city,
                        store.state,
                        store.postal_code,
                        store.country_code,
                    ] if value
                ),
            }
        )
        context["store_map_url"] = (
            f"https://www.google.com/maps/search/?api=1&query={quote_plus(context['store_map_query'])}"
            if context["store_map_query"] else ""
        )
        context["store_map_embed_url"] = (
            f"https://www.google.com/maps?q={quote_plus(context['store_map_query'])}&output=embed"
            if context["store_map_query"] else ""
        )
        return self.with_delivery_context(context)


class StoreRatingSubmitView(View):
    def post(self, request, *args, **kwargs):
        store = get_object_or_404(Store, slug=self.kwargs["slug"], status=Store.STATUS_ACTIVE, is_active=True)
        try:
            rating = int(request.POST.get("rating", "0"))
        except (TypeError, ValueError):
            rating = 0
        reviewer_name = (request.POST.get("name") or "Customer").strip()[:120]
        comment = (request.POST.get("comment") or "").strip()

        if rating < 1 or rating > 5:
            return JsonResponse({"status": "error", "message": "Please select a rating from 1 to 5."}, status=400)

        StoreRating.objects.create(
            store=store,
            reviewer_name=reviewer_name or "Customer",
            rating=rating,
            comment=comment,
            is_approved=False,
        )

        return JsonResponse(
            {
                "status": "success",
                "message": "Thanks. Your rating was submitted for approval.",
                "rating": str(store.rating),
                "count": store.ratings.filter(is_approved=True, is_active=True).count(),
            }
        )


class StoreRatingListView(View):
    """Return approved store feedback in small pages for the storefront modal."""

    def get(self, request, *args, **kwargs):
        store = get_object_or_404(Store, slug=self.kwargs["slug"], status=Store.STATUS_ACTIVE, is_active=True)
        ratings = store.ratings.filter(is_approved=True, is_active=True).order_by("-created_at")
        paginator = Paginator(ratings, 5)
        page_number = request.GET.get("page", 1)
        page = paginator.get_page(page_number)
        return JsonResponse(
            {
                "results": [
                    {
                        "name": rating.reviewer_name,
                        "rating": rating.rating,
                        "comment": rating.comment or "Shared a store rating without a comment.",
                        "date": rating.created_at.strftime("%b %d, %Y"),
                    }
                    for rating in page.object_list
                ],
                "pagination": {
                    "page": page.number,
                    "pages": paginator.num_pages,
                    "count": paginator.count,
                },
            }
        )


class CategoryPageView(StorefrontBaseMixin, TemplateView):
    template_name = "storefront/category_page.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = get_object_or_404(Category, slug=self.kwargs["slug"], is_active=True)
        descendant_ids = [category.id] + list(category.children.filter(is_active=True).values_list("id", flat=True))
        products = APPROVED_PRODUCT_QS.filter(category_id__in=descendant_ids).prefetch_related(
            Prefetch("media_items", queryset=ProductMedia.objects.filter(media_type=ProductMedia.TYPE_IMAGE).order_by("sort_order", "-is_primary")),
            "variants",
        ).order_by("-created_at")
        
        ignore_location = self.request.GET.get("ignore_location") == "1"
        location_payload = self.get_delivery_payload()
        products, other_location_msg, other_location_url = self.apply_location_filter(
            products, location_payload, ignore_location=ignore_location, is_store_qs=False
        )
        brand_ids = self.request.GET.getlist("brand_id")
        color_ids = self.request.GET.getlist("color_id")
        in_stock_only = self.request.GET.get("in_stock", "").strip() in {"1", "true", "yes", "on"}
        min_price_raw = self.request.GET.get("min_price")
        max_price_raw = self.request.GET.get("max_price")
        min_price = self.parse_decimal_query_value(min_price_raw)
        max_price = self.parse_decimal_query_value(max_price_raw)
        
        if brand_ids:
            products = products.filter(brand_id__in=brand_ids)
        if color_ids:
            products = products.filter(variants__attribute_values__option_id__in=color_ids).distinct()
        available_count = products.filter(stock_items__on_hand_quantity__gt=0).distinct().count()
        products = self.apply_stock_filter(products, in_stock_only=in_stock_only)

        if min_price is not None:
            products = products.filter(price__gte=min_price)
        if max_price is not None:
            products = products.filter(price__lte=max_price)
        sort_by = self.request.GET.get("sort", "relevance").strip()
        if sort_by == "price_asc":
            products = products.order_by("price", "-created_at")
        elif sort_by == "price_desc":
            products = products.order_by("-price", "-created_at")
        elif sort_by == "newest":
            products = products.order_by("-created_at")

        context["selected_category_ids"] = [str(category.id)]  # CategoryPageView implies the category is selected
        context["selected_brand_ids"] = brand_ids
        context["selected_color_ids"] = color_ids
        context["in_stock_only"] = in_stock_only
        context["in_stock_count"] = available_count
        context["all_brands"] = self.get_available_brands(products, selected_ids=brand_ids)
        context["all_categories"] = self.get_available_categories(products, selected_ids=context["selected_category_ids"])
        context["all_colors"] = self.get_available_colors(products, selected_ids=color_ids)
        context["min_price"] = self.normalize_query_value(min_price_raw, default="")
        context["max_price"] = self.normalize_query_value(max_price_raw, default="")
        context["sort_by"] = sort_by
        context["products_count"] = products.count()
        price_bounds = products.aggregate(min_price=Min("price"), max_price=Max("price"))
        context["price_floor"] = price_bounds["min_price"] if price_bounds["min_price"] is not None else Decimal("0.00")
        context["price_ceiling"] = price_bounds["max_price"] if price_bounds["max_price"] is not None else Decimal("0.00")

        context.update(
            {
                "page_title": category.name,
                "category": category,
                "child_categories": category.children.filter(is_active=True).order_by("sort_order", "name"),
                "products": products,
                "selected_brand_ids": brand_ids,
                "other_location_msg": other_location_msg,
                "other_location_url": other_location_url,
            }
        )
        return self.with_delivery_context(context)


class ProductListingPageView(StorefrontBaseMixin, TemplateView):
    template_name = "storefront/product_listing.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        category_slug = self.request.GET.get("category", "").strip()
        store_slug = self.request.GET.get("store", "").strip()
        
        category_ids = self.request.GET.getlist("category_id")
        brand_ids = self.request.GET.getlist("brand_id")
        color_ids = self.request.GET.getlist("color_id")
        in_stock_only = self.request.GET.get("in_stock", "").strip() in {"1", "true", "yes", "on"}
        min_price_raw = self.request.GET.get("min_price")
        max_price_raw = self.request.GET.get("max_price")
        min_price = self.parse_decimal_query_value(min_price_raw)
        max_price = self.parse_decimal_query_value(max_price_raw)
        
        products = APPROVED_PRODUCT_QS.prefetch_related(
            Prefetch("media_items", queryset=ProductMedia.objects.filter(media_type=ProductMedia.TYPE_IMAGE).order_by("sort_order", "-is_primary")),
            "variants",
        ).order_by("-created_at")

        retailer_filter = getattr(self, "retailer_filter", None)
        if retailer_filter is not None:
            products = products.filter(store__retailer=retailer_filter)
        
        ignore_location = self.request.GET.get("ignore_location") == "1"
        location_payload = self.get_delivery_payload()
        products, other_location_msg, other_location_url = self.apply_location_filter(
            products, location_payload, ignore_location=ignore_location, is_store_qs=False
        )
        
        if query:
            products = products.filter(Q(name__icontains=query) | Q(sku__icontains=query) | Q(description__icontains=query))
        if category_slug:
            products = products.filter(category__slug=category_slug)
        if store_slug:
            products = products.filter(store__slug=store_slug)
            
        if category_ids:
            products = products.filter(category_id__in=category_ids)
        if brand_ids:
            products = products.filter(brand_id__in=brand_ids)
        if color_ids:
            products = products.filter(variants__attribute_values__option_id__in=color_ids).distinct()
        available_count = products.filter(stock_items__on_hand_quantity__gt=0).distinct().count()
        products = self.apply_stock_filter(products, in_stock_only=in_stock_only)

        if min_price is not None:
            products = products.filter(price__gte=min_price)
        if max_price is not None:
            products = products.filter(price__lte=max_price)

        sort_by = self.request.GET.get("sort", "relevance").strip()
        if sort_by == "price_asc":
            products = products.order_by("price", "-created_at")
        elif sort_by == "price_desc":
            products = products.order_by("-price", "-created_at")
        elif sort_by == "newest":
            products = products.order_by("-created_at")

        products = self.prioritize_available_products(products, *({
            "price_asc": ("price", "-created_at"),
            "price_desc": ("-price", "-created_at"),
            "newest": ("-created_at",),
        }.get(sort_by, ("-created_at",))))

        context["all_categories"] = self.get_available_categories(products, selected_ids=category_ids)
        context["all_brands"] = self.get_available_brands(products, selected_ids=brand_ids)
        context["all_colors"] = self.get_available_colors(products, selected_ids=color_ids)
        price_bounds = products.aggregate(min_price=Min("price"), max_price=Max("price"))
        context["price_floor"] = price_bounds["min_price"] if price_bounds["min_price"] is not None else Decimal("0.00")
        context["price_ceiling"] = price_bounds["max_price"] if price_bounds["max_price"] is not None else Decimal("0.00")
        
        context.update(
            {
                "page_title": "Products",
                "products": products,
                "products_count": products.count(),
                "search_query": query,
                "selected_category": category_slug,
                "selected_store": store_slug,
                "selected_category_ids": category_ids,
                "selected_brand_ids": brand_ids,
                "selected_color_ids": color_ids,
                "in_stock_only": in_stock_only,
                "in_stock_count": available_count,
                "min_price": self.normalize_query_value(min_price_raw, default=""),
                "max_price": self.normalize_query_value(max_price_raw, default=""),
                "sort_by": sort_by,
                "other_location_msg": other_location_msg,
                "other_location_url": other_location_url,
                "store_page": False,
            }
        )
        return self.with_delivery_context(context)


class RetailerShopPageView(ProductListingPageView):
    """Retailer-level shop showing products from all of that retailer's stores."""

    def get_context_data(self, **kwargs):
        self.retailer_filter = get_object_or_404(
            Retailer.objects.select_related("account"),
            Q(account__slug=self.kwargs["slug"]) | Q(stores__slug=self.kwargs["slug"]),
            status=Retailer.STATUS_APPROVED,
            is_active=True,
        )
        context = super().get_context_data(**kwargs)
        retailer = self.retailer_filter
        products = context["products"]
        context.update(
            {
                "retailer": retailer,
                "page_title": retailer.display_name or retailer.legal_name,
                "products": products,
                "products_count": products.count(),
                "store_page": True,
            }
        )
        return context


class SellerComparisonPageView(StorefrontBaseMixin, TemplateView):
    template_name = "storefront/seller_comparison.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        delivery_payload = self.get_delivery_payload()
        comparisons = defaultdict(list)
        if query:
            matches = APPROVED_PRODUCT_QS.filter(
                Q(name__icontains=query) | Q(model_name__icontains=query) | Q(barcode__icontains=query)
            ).order_by("model_name", "name", "discount_price", "price")[:36]
            for product in matches:
                family = self.resolve_product_family_value(product)
                stock = self.get_stock_snapshot(product)
                delivery = self.get_delivery_estimate(product, location_payload=delivery_payload)
                comparisons[family].append(
                    {
                        "product": product,
                        "retailer_name": product.store.name,
                        "location": ", ".join(filter(None, [product.store.city, product.store.country_code])),
                        "price": product.discount_price or product.price,
                        "stock": stock["label"],
                        "delivery_estimate": delivery["date_label"],
                        "rating": product.store.rating,
                        "is_serviceable": delivery["is_serviceable"],
                    }
                )
        context.update(
            {
                "page_title": "Seller Comparison",
                "search_query": query,
                "comparison_groups": dict(comparisons),
            }
        )
        return self.with_delivery_context(context)


class CartPageView(StorefrontBaseMixin, TemplateView):
    template_name = "storefront/cart.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"page_title": "Cart", **self.get_cart_totals(self.request)})
        return self.with_delivery_context(context)


class CheckoutPageView(StorefrontBaseMixin, TemplateView):
    template_name = "storefront/checkout.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        delivery_payload = self.get_delivery_payload()
        cart = ensure_request_cart(self.request)
        recalculate_cart(cart, location_payload=delivery_payload)
        totals = self.get_cart_totals(self.request)
        delivery_items = []
        for item in totals["items"]:
            estimate = self.get_delivery_estimate(item.product, location_payload=delivery_payload)
            delivery_items.append({"item": item, "delivery": estimate})
        address_queryset = []
        selected_address = None
        address_form = None
        checkout_form = None
        if self.request.user.is_authenticated:
            address_queryset = self.request.user.addresses.filter(is_active=True).order_by("-is_default", "-updated_at")
            selected_address = resolve_checkout_address(self.request.user)
            
            initial_address_data = {}
            if not selected_address:
                from apps.inventory.delivery import SESSION_LOCATION_KEY
                session_loc = self.request.session.get(SESSION_LOCATION_KEY)
                if session_loc and session_loc.get("pincode"):
                    initial_address_data["postal_code"] = session_loc.get("pincode")
                    if session_loc.get("city"):
                        initial_address_data["city"] = session_loc.get("city")
                    if session_loc.get("state") or session_loc.get("region"):
                        initial_address_data["state"] = session_loc.get("state") or session_loc.get("region")

            address_form = UserAddressForm(prefix="address", instance=selected_address, initial=initial_address_data)
            checkout_form = CheckoutSelectionForm(
                initial={
                    "address_id": getattr(selected_address, "id", None),
                    "payment_method": build_payment_method_choices()[0][0],
                },
                payment_choices=build_payment_method_choices(),
                prefix="checkout",
            )
        context.update(
            {
                "page_title": "Checkout",
                **totals,
                "delivery_items": delivery_items,
                "address_book": address_queryset,
                "selected_address": selected_address,
                "address_form": address_form,
                "checkout_form": checkout_form,
                "requires_login_for_order": not self.request.user.is_authenticated,
            }
        )
        return self.with_delivery_context(context)


from django.contrib.auth import login
from django.urls import reverse_lazy
from django.views.generic import CreateView
from apps.storefront.forms import CustomerRegistrationForm

class CustomerRegisterView(StorefrontBaseMixin, CreateView):
    template_name = "storefront/register.html"
    form_class = CustomerRegistrationForm
    success_url = reverse_lazy("storefront:customer-dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"page_title": "Register"})
        return self.with_delivery_context(context)

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response

class CustomerDashboardView(LoginRequiredMixin, StorefrontBaseMixin, TemplateView):
    template_name = "storefront/customer_dashboard.html"
    login_url = reverse_lazy("storefront:login")

    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        orders = (
            Order.objects.filter(customer=self.request.user)
            .prefetch_related("items", "return_requests", "timeline_entries", "payments", "shipments")
            .order_by("-created_at")
        )
        context.update({"page_title": "Customer Dashboard", "orders": orders})
        return self.with_delivery_context(context)


class ContactPageView(StorefrontBaseMixin, TemplateView):
    template_name = "storefront/contact.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        primary_store = Store.objects.filter(status=Store.STATUS_ACTIVE, is_active=True).order_by("name").first()
        context.update({"page_title": "Contact", "primary_store": primary_store})
        return self.with_delivery_context(context)


class SetDeliveryLocationView(View):
    def post(self, request):
        pincode = request.POST.get("pincode", "").strip()
        latitude = request.POST.get("latitude", "").strip()
        longitude = request.POST.get("longitude", "").strip()
        source = request.POST.get("source", "manual").strip() or "manual"
        redirect_to = request.POST.get("next") or request.META.get("HTTP_REFERER") or reverse("storefront:home")
        
        from apps.inventory.delivery import resolve_geolocation_label
        
        label = pincode or resolve_geolocation_label(latitude, longitude)
        if not pincode and latitude and longitude:
            resolved = resolve_geolocation_label(latitude, longitude)
            if resolved and resolved != "Detected location":
                # Assuming the label returned IS the pincode for valid matches, or let's just 
                # extract it using another method, but for now we'll set pincode to resolved if it's numeric/short
                pincode = resolved
        payload = set_request_location(
            request,
            pincode=pincode,
            latitude=latitude,
            longitude=longitude,
            source=source,
            label=label,
        )
        if payload.get("pincode") or payload.get("latitude"):
            messages.success(request, f"Delivery location set to {payload.get('label', 'selected area')}.")
        else:
            messages.error(request, "Enter a valid pincode or use location detection.")
        return redirect(redirect_to)


class ClearDeliveryLocationView(View):
    def post(self, request):
        clear_request_location(request)
        messages.success(request, "Delivery location cleared.")
        return redirect(request.POST.get("next") or request.META.get("HTTP_REFERER") or reverse("storefront:home"))


class AddToCartView(View):
    def post(self, request, product_id):
        product = get_object_or_404(APPROVED_PRODUCT_QS, id=product_id)
        try:
            quantity = int(request.POST.get("quantity", 1))
        except (TypeError, ValueError):
            quantity = 1
        quantity = max(quantity, 1)

        variant_id = request.POST.get("variant_id")
        variant = None
        unit_price = float(product.discount_price or product.price)
        if variant_id:
            from apps.catalog.models import ProductVariant
            variant = ProductVariant.objects.filter(product=product, id=variant_id).first()
            if variant:
                unit_price = float(variant.discount_price or variant.price)

        cart = ensure_request_cart(request)
        try:
            add_product_to_cart(cart=cart, product=product, quantity=quantity, variant=variant)
        except ValueError as exc:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "message": str(exc)})
            messages.error(request, str(exc))
            return redirect(request.META.get("HTTP_REFERER", reverse("storefront:cart")))
        
        session_cart = request.session.get("cart", {})
        key = cart_session_key(product, variant)
        item = session_cart.get(key, {"quantity": 0, "unit_price": unit_price})
        item["quantity"] += quantity
        item["unit_price"] = unit_price
        if variant:
            item["variant_id"] = str(variant.id)
        session_cart[key] = item
        request.session["cart"] = session_cart
        request.session.modified = True
        
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            cart_count = sum(item.get("quantity", 1) for item in session_cart.values())
            return JsonResponse({"success": True, "cart_count": cart_count, "message": f"{product.name} added to cart."})
        
        messages.success(request, f"{product.name} added to cart.")
        return redirect(request.META.get("HTTP_REFERER", reverse("storefront:cart")))


class BuyNowView(View):
    def post(self, request, product_id):
        product = get_object_or_404(APPROVED_PRODUCT_QS, id=product_id)
        try:
            quantity = int(request.POST.get("quantity", 1))
        except (TypeError, ValueError):
            quantity = 1
        quantity = max(quantity, 1)

        variant_id = request.POST.get("variant_id")
        variant = None
        unit_price = float(product.discount_price or product.price)
        if variant_id:
            from apps.catalog.models import ProductVariant
            variant = ProductVariant.objects.filter(product=product, id=variant_id).first()
            if variant:
                unit_price = float(variant.discount_price or variant.price)

        request.session["cart"] = {
            cart_session_key(product, variant): {
                "quantity": quantity,
                "unit_price": unit_price,
                "variant_id": str(variant.id) if variant else None,
            }
        }
        request.session.modified = True
        cart = ensure_request_cart(request)
        cart.items.all().delete()
        try:
            add_product_to_cart(cart=cart, product=product, quantity=quantity, variant=variant)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(request.META.get("HTTP_REFERER", reverse("storefront:products")))
        messages.success(request, f"{product.name} added for instant checkout.")
        return redirect("storefront:checkout")


class RemoveFromCartView(View):
    def post(self, request, product_id):
        cart = ensure_request_cart(request)
        cart_item = cart.items.filter(product_id=product_id).first()
        if cart_item:
            cart_item.delete()
            recalculate_cart(cart)
        session_cart = request.session.get("cart", {})
        for key in list(session_cart.keys()):
            if str(key).split(":", 1)[0] == str(product_id):
                session_cart.pop(key, None)
        request.session["cart"] = session_cart
        request.session.modified = True
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True, "cart_count": sum(item["quantity"] for item in session_cart.values())})
        messages.success(request, "Item removed from cart.")
        return redirect(request.META.get("HTTP_REFERER", reverse("storefront:cart")))


class UpdateCartItemView(View):
    def post(self, request, product_id):
        try:
            quantity = int(request.POST.get("quantity", 1))
        except (TypeError, ValueError):
            quantity = 1
        cart = ensure_request_cart(request)
        cart_item = get_object_or_404(cart.items, product_id=product_id)
        try:
            update_cart_item_quantity(cart_item=cart_item, quantity=quantity)
        except ValueError as exc:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "message": str(exc)})
            messages.error(request, str(exc))
            return redirect(request.META.get("HTTP_REFERER", reverse("storefront:cart")))
        session_cart = request.session.get("cart", {})
        if quantity <= 0:
            session_cart.pop(cart_session_key(cart_item.product, cart_item.variant), None)
        else:
            session_cart[cart_session_key(cart_item.product, cart_item.variant)] = {
                "quantity": quantity,
                "unit_price": float(cart_item.discount_price),
                "variant_id": str(cart_item.variant_id) if cart_item.variant_id else None,
            }
        request.session["cart"] = session_cart
        request.session.modified = True
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True, "quantity": quantity, "cart_count": sum(item["quantity"] for item in session_cart.values())})
        messages.success(request, "Cart updated.")
        return redirect(request.META.get("HTTP_REFERER", reverse("storefront:cart")))


class AddToWishlistView(View):
    def post(self, request, product_id):
        product = get_object_or_404(APPROVED_PRODUCT_QS, id=product_id)
        wishlist = request.session.get("wishlist", [])
        pid = str(product.id)
        added = False
        
        if pid in wishlist:
            wishlist.remove(pid)
            msg = f"{product.name} removed from wishlist."
        else:
            wishlist.append(pid)
            added = True
            msg = f"{product.name} added to wishlist."
            
        request.session["wishlist"] = wishlist
        request.session.modified = True
        
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True, "added": added, "wishlist_count": len(wishlist), "message": msg})
            
        messages.success(request, msg)
        return redirect(request.META.get("HTTP_REFERER", reverse("storefront:products")))


class PlaceOrderView(LoginRequiredMixin, View):
    login_url = reverse_lazy("storefront:login")

    def post(self, request):
        cart = ensure_request_cart(request)
        sync_session_cart_to_db(request, cart=cart)
        payment_choices = build_payment_method_choices()
        checkout_form = CheckoutSelectionForm(
            request.POST,
            payment_choices=payment_choices,
            prefix="checkout",
        )
        address_id = request.POST.get("checkout-address_id")
        selected_address = resolve_checkout_address(request.user, address_id=address_id) if address_id else None
        address_form = UserAddressForm(
            request.POST,
            prefix="address",
            instance=selected_address,
        )
        if not selected_address:
            if address_form.is_valid():
                selected_address = address_form.save(commit=False)
                selected_address.user = request.user
                selected_address.save()
            else:
                messages.error(request, "Select an address or enter a valid shipping address.")
                return redirect("storefront:checkout")
        if not checkout_form.is_valid():
            messages.error(request, "Select a payment method to continue.")
            return redirect("storefront:checkout")
        try:
            orders = create_orders_from_cart(
                request=request,
                cart=cart,
                address=selected_address,
                payment_method=checkout_form.cleaned_data["payment_method"],
                note=checkout_form.cleaned_data.get("note", ""),
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("storefront:cart")
        for order in orders:
            confirm_order(order, actor=request.user)
        request.session["cart"] = {}
        request.session.modified = True
        numbers = ", ".join(order.number for order in orders)
        messages.success(request, f"Order placed successfully: {numbers}.")
        return redirect("storefront:customer-dashboard")


class WishlistPageView(StorefrontBaseMixin, TemplateView):
    template_name = "storefront/wishlist.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wishlist_ids = self.request.session.get("wishlist", [])
        products = APPROVED_PRODUCT_QS.filter(id__in=wishlist_ids).prefetch_related("media_items")
        context.update({"page_title": "Wishlist", "products": products})
        return self.with_delivery_context(context)

class RemoveFromWishlistView(View):
    def post(self, request, product_id):
        wishlist = request.session.get("wishlist", [])
        if str(product_id) in wishlist:
            wishlist.remove(str(product_id))
        request.session["wishlist"] = wishlist
        request.session.modified = True
        messages.success(request, "Item removed from wishlist.")
        return redirect("storefront:wishlist")

class LiveSearchView(StorefrontBaseMixin, View):
    def get(self, request):
        q = request.GET.get("q", "").strip()
        if not q or len(q) < 2:
            return JsonResponse({"results": []})
        
        query_words = q.split()
        qs = APPROVED_PRODUCT_QS
        store_slug = request.GET.get("store")
        if store_slug:
            qs = qs.filter(store__slug=store_slug)
            other_location_msg = "Do you want to search products from stores in another location?"
            other_location_url = f"/products/?q={q}&ignore_location=1"
        else:
            location_payload = self.get_delivery_payload()
            qs, other_location_msg, other_location_url = self.apply_location_filter(qs, location_payload, is_store_qs=False)
            if not other_location_url and other_location_msg:
                other_location_url = f"/products/?q={q}&ignore_location=1"
            elif other_location_msg:
                # url returned by apply_location_filter includes query params but doesn't have the path.
                # Since LiveSearchView is called on /live-search/, we need it to point to /products/
                other_location_url = f"/products/?q={q}&ignore_location=1"
            
        for word in query_words:
            qs = qs.filter(
                Q(name__icontains=word) | 
                Q(brand__name__icontains=word) | 
                Q(category__name__icontains=word) |
                Q(variants__name__icontains=word) |
                Q(variants__attribute_values__attribute__name__icontains=word) |
                Q(variants__attribute_values__option__value__icontains=word) |
                Q(variants__attribute_values__value__icontains=word)
            )
        products = qs.distinct()[:5]
        
        results = []
        for p in products:
            image_url = ""
            if p.media_items.exists() and p.media_items.first().file:
                image_url = p.media_items.first().file.url
            
            variants = p.variants.all()
            has_variants = any(v.name and v.name.lower() != "default variant" for v in variants)
            
            if has_variants:
                real_variants = [v for v in variants if v.name and v.name.lower() != "default variant" and v.available_qty > 0]
                
                # Check if the product name/brand/category directly matches the full query
                product_matched = (q.lower() in p.name.lower()) or (p.brand and q.lower() in p.brand.name.lower()) or (p.category and q.lower() in p.category.name.lower())
                
                # If product itself didn't match the whole string, filter variants to those that match the words
                if not product_matched:
                    filtered_variants = []
                    for v in real_variants:
                        # Check if variant name or attributes match the query words that didn't match the product
                        match = True
                        for word in query_words:
                            word_lower = word.lower()
                            if not (word_lower in p.name.lower() or word_lower in (p.brand.name.lower() if p.brand else "") or word_lower in (p.category.name.lower() if p.category else "")):
                                if word_lower not in v.name.lower():
                                    match = False
                                    break
                        if match:
                            filtered_variants.append(v)
                    if filtered_variants:
                        real_variants = filtered_variants
                
                for v in real_variants:
                    results.append({
                        "id": f"{p.id}-{v.id}",
                        "name": f"{p.name} - {v.name}",
                        "price": str(v.discount_price or v.price),
                        "image_url": image_url,
                        "variants": "",
                        "url": reverse("catalog:product-detail", kwargs={"slug": p.slug}) + f"?variant={v.id}"
                    })
            else:
                if p.available_qty > 0:
                    results.append({
                        "id": str(p.id),
                        "name": p.name,
                        "price": str(p.discount_price or p.price),
                        "image_url": image_url,
                        "variants": "",
                        "url": reverse("catalog:product-detail", kwargs={"slug": p.slug})
                    })
        
        # limit total search results to 8
        results = results[:8]
        return JsonResponse({"results": results, "other_location_msg": other_location_msg, "other_location_url": other_location_url, "query": q})

class SetLocationView(View):
    def get(self, request):
        if request.GET.get("clear") == "true":
            from apps.inventory.delivery import clear_request_location
            clear_request_location(request)
            return JsonResponse({"status": "cleared"})
            
        pincode = request.GET.get("pincode", "")
        latitude = request.GET.get("latitude")
        longitude = request.GET.get("longitude")
        
        from apps.inventory.delivery import set_request_location
        set_request_location(request, pincode=pincode, latitude=latitude, longitude=longitude)
        
        return JsonResponse({"status": "success"})

class ComparePageView(StorefrontBaseMixin, TemplateView):
    template_name = "storefront/compare.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        compare_list = self.request.session.get("compare_list", [])
        products = APPROVED_PRODUCT_QS.filter(id__in=compare_list)
        
        product_data = []
        for p in products:
            product_data.append({
                "product": p,
                "price": p.discount_price or p.price,
                "stock": self.get_stock_snapshot(p),
                "delivery": self.get_delivery_estimate(p, location_payload=self.get_delivery_payload())
            })
        
        context["compare_products"] = product_data
        return context

class AddToCompareView(View):
    def post(self, request, product_id, *args, **kwargs):
        compare_list = request.session.get("compare_list", [])
        pid = str(product_id)
        added = False
        msg = ""
        success = True
        
        if pid in compare_list:
            compare_list.remove(pid)
            msg = "Product removed from compare."
        else:
            if len(compare_list) >= 4:
                msg = "You can compare up to 4 products at a time."
                success = False
            else:
                compare_list.append(pid)
                added = True
                msg = "Product added to compare."
                
        if success:
            request.session["compare_list"] = compare_list
            request.session.modified = True
            
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": success, "added": added, "compare_count": len(compare_list), "message": msg})
            
        if success:
            messages.success(request, msg)
        else:
            messages.warning(request, msg)
        return redirect(request.META.get("HTTP_REFERER", "storefront:home"))

class RemoveFromCompareView(View):
    def post(self, request, product_id, *args, **kwargs):
        compare_list = request.session.get("compare_list", [])
        removed = False
        if str(product_id) in compare_list:
            compare_list.remove(str(product_id))
            request.session["compare_list"] = compare_list
            request.session.modified = True
            removed = True
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({
                "success": True,
                "removed": removed,
                "compare_count": len(compare_list),
                "message": "Product removed from compare." if removed else "Product was not in compare.",
            })
        if removed:
            messages.success(request, "Product removed from compare.")
        return redirect(request.META.get("HTTP_REFERER", "storefront:home"))
