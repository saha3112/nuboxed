from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q
from django.utils import timezone

from apps.settings_app.models import SaleCountdownSetting


def get_effective_sale_price(product, variant=None):
    """Return the active rule price, falling back to the product price.

    A live countdown percentage intentionally takes precedence over the
    product/variant discount price. Once the rule is inactive, expired,
    deleted, or has no percentage, the catalogue discount is used again.
    """
    source = variant or product
    base_price = Decimal(source.price or 0)
    catalogue_price = Decimal(source.discount_price or base_price)
    countdown = get_effective_sale_countdown(product, variant=variant)
    percentage = Decimal(str(countdown.get("discount_percentage") or 0)) if countdown.get("enabled") else Decimal("0")
    if percentage > 0 and base_price > 0:
        rule_price = (base_price * (Decimal("100") - percentage) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {"price": rule_price, "compare_price": base_price, "discount_percentage": percentage, "source": "rule"}
    catalogue_percentage = ((base_price - catalogue_price) / base_price * Decimal("100")) if base_price and catalogue_price < base_price else Decimal("0")
    return {"price": catalogue_price, "compare_price": base_price if catalogue_price < base_price else None, "discount_percentage": catalogue_percentage, "source": "catalogue"}


def get_effective_sale_countdown(product, variant=None):
    """Return the countdown text/time after applying override precedence."""
    now = timezone.now()
    if getattr(product, "sale_override_enabled", False):
        ends_at = product.sale_ends_at
        if not ends_at or ends_at <= now:
            return {
                "message": "",
                "ends_at": None,
                "starts_at": None,
                "source": "expired",
                "enabled": False,
            }
        return {
            "message": product.sale_title or "Hurry up! Sale ends in:",
            "ends_at": ends_at,
            "source": "product",
            "enabled": True,
        }

    category_ids = []
    category = getattr(product, "category", None)
    while category:
        category_ids.append(category.id)
        category = category.parent

    matching_settings = getattr(product, "_sale_countdown_matching_settings", None)
    if matching_settings is None:
        matching_settings = list(SaleCountdownSetting.objects.filter(
            Q(category_id__isnull=True) | Q(category_id__in=category_ids),
            Q(product_id__isnull=True) | Q(product_id=product.id),
            Q(retailer_id__isnull=True) | Q(retailer_id=getattr(product, "retailer_id", None)),
            deleted_at__isnull=True,
        ).select_related("category"))
        product._sale_countdown_matching_settings = matching_settings
    settings = [item for item in matching_settings if item.is_active and
                (item.starts_at is None or item.starts_at <= now) and
                (item.ends_at is None or item.ends_at >= now)]

    retailer_id = getattr(product, "retailer_id", None)
    variant_id = str(getattr(variant, "id", "")) if variant else ""

    # A product rule with an empty list applies to every variant. A non-empty
    # list is the explicit multi-variant scope saved by the retailer form.
    settings = [
        item for item in settings
        if (not item.variant_id or item.variant_id == getattr(variant, "id", None))
        and (not item.selected_variant_ids or variant_id in {str(value) for value in item.selected_variant_ids})
    ]
    category_rank = {category_id: index for index, category_id in enumerate(category_ids)}

    def rank(setting):
        is_retailer = setting.retailer_id == retailer_id
        has_category = bool(setting.category_id)
        has_product = bool(setting.product_id)
        has_variant = bool(setting.variant_id) or bool(setting.selected_variant_ids)
        # Retailer category > global category > retailer global > global.
        return (
            6 if is_retailer and has_variant else
            5 if is_retailer and has_product else
            4 if is_retailer and has_category else
            3 if has_category else
            2 if is_retailer else 1,
            -category_rank.get(setting.category_id, 999),
            setting.updated_at,
        )

    ordered_settings = sorted(list(settings), key=rank, reverse=True)
    setting = ordered_settings[0] if ordered_settings else None
    if setting:
        message = setting.message
        if not message:
            message = next((item.message for item in ordered_settings[1:] if item.message), None)
        # A rule may intentionally omit an end date. If the product already
        # has a valid future sale end, reuse it so the effective sale price and
        # countdown stay consistent across cards, Quick View, and detail pages.
        rule_ends_at = setting.ends_at
        if not rule_ends_at:
            product_ends_at = getattr(product, "sale_ends_at", None)
            if product_ends_at and product_ends_at > now:
                rule_ends_at = product_ends_at
        return {
            "message": message or product.sale_title or "Hurry up! Sale ends in:",
            "starts_at": setting.starts_at,
            "ends_at": rule_ends_at,
            "source": "category" if setting.category_id else "global",
            "enabled": True,
            "discount_percentage": setting.discount_percentage,
        }
    # An inactive global rule is the admin's explicit kill switch. Keep the
    # product-level fallback for installations that have never configured a
    # global countdown at all.
    if any(item.retailer_id is None and item.category_id is None and not item.is_active for item in matching_settings):
        return {
            "message": "",
            "ends_at": None,
            "starts_at": None,
            "source": "disabled",
            "enabled": False,
        }
    # Product.sale_ends_at has a default value for legacy catalogue records;
    # it is not, by itself, proof that a sale is active. Only expose the
    # default countdown when the selected product/variant has a real catalogue
    # discount and its end time is still in the future.
    source = variant or product
    base_price = Decimal(source.price or 0)
    sale_price = Decimal(source.discount_price or base_price)
    ends_at = getattr(product, "sale_ends_at", None)
    has_active_catalogue_sale = bool(ends_at and ends_at > now and sale_price < base_price)
    if not has_active_catalogue_sale:
        return {
            "message": "",
            "ends_at": None,
            "starts_at": None,
            "source": "product-default",
            "enabled": False,
        }
    return {
        "message": product.sale_title or "Hurry up! Sale ends in:",
        "ends_at": ends_at,
        "starts_at": None,
        "source": "product-default",
        "enabled": True,
    }
