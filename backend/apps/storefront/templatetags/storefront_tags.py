from django import template

register = template.Library()


@register.filter
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except (TypeError, ValueError):
        return 0


@register.filter
def get_key(data, key):
    return data.get(str(key))
