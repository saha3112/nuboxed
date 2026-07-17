from django import template

register = template.Library()


@register.filter
def get_item(data, key):
    return data.get(key)


@register.filter
def attr(obj, key):
    return getattr(obj, key)


@register.filter
def titlecase_slug(value):
    return str(value).replace("-", " ").title()


@register.filter
def is_deleted_record(obj):
    deleted_at = getattr(obj, "deleted_at", None)
    if deleted_at:
        return True
    if hasattr(obj, "is_active"):
        return not bool(getattr(obj, "is_active"))
    return False
