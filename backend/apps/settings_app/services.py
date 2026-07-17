from django.db.models import Q

from apps.settings_app.models import SaleCountdownSetting


def get_effective_sale_countdown(product):
    """Return the countdown text/time after applying override precedence."""
    if getattr(product, "sale_override_enabled", False):
        return {
            "message": product.sale_title or "Hurry up! Sale ends in:",
            "ends_at": product.sale_ends_at,
            "source": "product",
        }

    category_ids = []
    category = getattr(product, "category", None)
    while category:
        category_ids.append(category.id)
        category = category.parent

    settings = SaleCountdownSetting.objects.filter(
        Q(category_id__isnull=True) | Q(category_id__in=category_ids),
        Q(retailer_id__isnull=True) | Q(retailer_id=getattr(product, "retailer_id", None)),
        is_active=True,
    ).select_related("category")

    retailer_id = getattr(product, "retailer_id", None)
    category_rank = {category_id: index for index, category_id in enumerate(category_ids)}

    def rank(setting):
        is_retailer = setting.retailer_id == retailer_id
        has_category = bool(setting.category_id)
        # Retailer category > global category > retailer global > global.
        return (
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
        return {
            "message": message or product.sale_title or "Hurry up! Sale ends in:",
            "ends_at": setting.ends_at,
            "source": "category" if setting.category_id else "global",
        }
    return {
        "message": product.sale_title or "Hurry up! Sale ends in:",
        "ends_at": product.sale_ends_at,
        "source": "product-default",
    }
