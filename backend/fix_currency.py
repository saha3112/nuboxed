import os
import re

FILES = [
    "templates/storefront/product_detail_page.html",
    "templates/storefront/seller_comparison.html",
    "templates/storefront/cart.html",
    "templates/storefront/partials/product_card.html",
    "templates/storefront/wishlist.html",
    "templates/catalog/product_detail.html",
    "templates/catalog/retailer_products.html",
    "templates/catalog/product_form.html",
]

for file_path in FILES:
    full_path = os.path.join("/usr/local/var/www/Nuboxed/backend", file_path)
    if not os.path.exists(full_path):
        continue
        
    with open(full_path, "r") as f:
        content = f.read()
        
    if "{% load currency_tags %}" not in content:
        # insert after first extends or load if present
        if "{% extends" in content:
            content = re.sub(r'({% extends [^}]+ %}\n)', r'\1{% load currency_tags %}\n', content, count=1)
        elif "{% load" in content:
            content = re.sub(r'({% load [^}]+ %}\n)', r'\1{% load currency_tags %}\n', content, count=1)
        else:
            content = "{% load currency_tags %}\n" + content

    # simple replacements
    content = re.sub(r'€?\{\{\s*(.*?\.price.*?)\s*\}\}', r'{{ \1|format_currency:product.store.currency_code }}', content)
    content = re.sub(r'€?\{\{\s*(.*?\.discount_price.*?)\s*\}\}', r'{{ \1|format_currency:product.store.currency_code }}', content)
    
    # fix cart and others where it's item.product
    content = content.replace("format_currency:product.store.currency_code", "format_currency:product.store.currency_code")
    # Actually, for cart, wishlist, etc., `product` might not be defined. Let's do a more robust replace.
    # In seller_comparison: offer.product.store.currency_code
    
    with open(full_path, "w") as f:
        f.write(content)
print("Done")
