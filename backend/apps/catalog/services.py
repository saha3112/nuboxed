from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.catalog.models import Category, Product
from apps.notifications.services import send_notification_event

def unique_slug(model, value, field_name="slug"):
    base = slugify(value) or "item"
    slug = base
    index = 1
    while model.objects.filter(**{field_name: slug}).exists():
        index += 1
        slug = f"{base}-{index}"
    return slug


def unique_sku(model, base_value):
    base = slugify(base_value).replace("-", "").upper() or "SKU"
    sku = base[:32]
    index = 1
    while model.objects.filter(sku=sku).exists():
        index += 1
        sku = f"{base[:28]}{index:04d}"
    return sku


def split_comma_values(value):
    names = []
    seen = set()
    for item in (value or "").split(","):
        name = item.strip()
        key = name.lower()
        if name and key not in seen:
            names.append(name)
            seen.add(key)
    return names


@transaction.atomic
def sync_split_phone_models_from_combined(combined_model, previous_names=None):
    from apps.catalog.models import PhoneModel

    names = split_comma_values(combined_model.name)
    if len(names) < 2:
        removed_names = set(previous_names or []) - set(names)
        if removed_names:
            PhoneModel.objects.filter(
                platform=combined_model.platform,
                brand=combined_model.brand,
                name__in=removed_names,
            ).exclude(pk=combined_model.pk).update(is_active=False)
        return []

    normalized = []
    for name in names:
        model = (
            PhoneModel.objects.filter(
                platform=combined_model.platform,
                brand=combined_model.brand,
                name__iexact=name,
            )
            .exclude(pk=combined_model.pk)
            .first()
        )
        if model is None:
            model = PhoneModel.objects.create(
                platform=combined_model.platform,
                brand=combined_model.brand,
                name=name,
                released_year=combined_model.released_year,
                sort_order=combined_model.sort_order,
            )
        else:
            update_fields = []
            if not model.is_active:
                model.is_active = True
                update_fields.append("is_active")
            if combined_model.released_year and model.released_year != combined_model.released_year:
                model.released_year = combined_model.released_year
                update_fields.append("released_year")
            if update_fields:
                update_fields.append("updated_at")
                model.save(update_fields=update_fields)
        normalized.append(model)

    removed_names = set((previous_names or [])) - set(names)
    if removed_names:
        PhoneModel.objects.filter(
            platform=combined_model.platform,
            brand=combined_model.brand,
            name__in=removed_names,
        ).exclude(pk=combined_model.pk).update(is_active=False)

    return normalized


@transaction.atomic
def normalize_comma_separated_phone_models():
    from apps.catalog.models import PhoneModel

    normalized = []
    combined_models = (
        PhoneModel.objects.select_related("platform", "brand")
        .filter(name__contains=",")
        .order_by("platform__name", "brand__name", "name")
    )
    for combined_model in combined_models:
        names = split_comma_values(combined_model.name)
        if len(names) < 2:
            continue

        normalized.extend(sync_split_phone_models_from_combined(combined_model))

    return normalized


@transaction.atomic
def reorder_category(category: Category, parent=None, sort_order=0):
    category.parent = parent
    category.sort_order = sort_order
    category.save(update_fields=["parent", "sort_order", "updated_at"])
    return category


@transaction.atomic
def approve_product(product: Product, approver, notes=""):
    product.status = Product.STATUS_APPROVED
    product.approved_at = timezone.now()
    product.approved_by = approver
    product.approval_notes = notes
    product.save(update_fields=["status", "approved_at", "approved_by", "approval_notes", "updated_at"])
    
    user = product.retailer.account.owner if (product.retailer and product.retailer.account) else None
    send_notification_event(
        event_name="product_moderation",
        context={"product_name": product.name, "status": "APPROVED"},
        user=user
    )
    
    return product


@transaction.atomic
def reject_product(product: Product, approver, notes=""):
    product.status = Product.STATUS_REJECTED
    product.approved_at = timezone.now()
    product.approved_by = approver
    product.approval_notes = notes
    product.save(update_fields=["status", "approved_at", "approved_by", "approval_notes", "updated_at"])
    
    user = product.retailer.account.owner if (product.retailer and product.retailer.account) else None
    send_notification_event(
        event_name="product_moderation",
        context={"product_name": product.name, "status": "REJECTED"},
        user=user
    )
    
    return product
