from django import template
from django.utils.safestring import mark_safe

register = template.Library()

CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "INR": "₹",
    "AUD": "A$",
    "CAD": "C$",
    "JPY": "¥",
    "CNY": "¥",
    "BDT": "৳",
    "SGD": "S$",
    "AED": "د.إ",
}

@register.filter
def format_currency(value, currency_code="EUR"):
    if value is None:
        return ""
    try:
        val = float(value)
    except (ValueError, TypeError):
        return value
        
    symbol = CURRENCY_SYMBOLS.get(currency_code.upper(), currency_code.upper() + " ")
    
    # Format the number with 2 decimal places
    formatted_val = f"{val:,.2f}"
    
    # Return formatted string with symbol
    return f"{symbol}{formatted_val}"


@register.filter
def currency_symbol(currency_code="EUR"):
    return CURRENCY_SYMBOLS.get(str(currency_code or "EUR").upper(), str(currency_code or "EUR").upper() + " ")


@register.filter
def currency_amount(value):
    if value is None:
        return ""
    try:
        return f"{float(value):,.2f}"
    except (ValueError, TypeError):
        return value
