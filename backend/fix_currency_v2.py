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
        
    # Clean up double formats
    content = content.replace("|format_currency:product.store.currency_code|format_currency:product.store.currency_code", "")
    content = content.replace("|format_currency:product.store.currency_code", "")
    content = content.replace("|format_currency:object.store.currency_code", "")
    content = content.replace("|format_currency:offer.product.store.currency_code", "")
    content = content.replace("|format_currency:item.product.store.currency_code", "")
    content = content.replace("€", "") # remove hardcoded euro signs
    content = content.replace("₹", "") # remove hardcoded rupee signs

    # Make specific replacements based on the file content manually for exact precision
    if "product_detail_page.html" in file_path:
        content = content.replace("{{ object.discount_price|default:object.price }}", "{{ object.discount_price|default:object.price|format_currency:object.store.currency_code }}")
        content = content.replace("{{ object.price }}", "{{ object.price|format_currency:object.store.currency_code }}")
        content = content.replace("{{ offer.product.discount_price|default:offer.product.price }}", "{{ offer.product.discount_price|default:offer.product.price|format_currency:offer.product.store.currency_code }}")
        
    if "seller_comparison.html" in file_path:
        content = content.replace("{{ offer.price }}", "{{ offer.price|format_currency:offer.product.store.currency_code }}")
        
    if "cart.html" in file_path:
        content = content.replace("{{ item.quantity }} x {{ item.discount_price }}", "{{ item.quantity }} x {{ item.discount_price|format_currency:item.product.store.currency_code }}")

    if "product_card.html" in file_path or "wishlist.html" in file_path or "retailer_products.html" in file_path:
        content = content.replace("{{ product.discount_price|default:product.price }}", "{{ product.discount_price|default:product.price|format_currency:product.store.currency_code }}")
        content = content.replace("{{ product.price }}", "{{ product.price|format_currency:product.store.currency_code }}")
        content = content.replace("{{ product.discount_price }}", "{{ product.discount_price|format_currency:product.store.currency_code }}")
        content = content.replace("{{ product.default_variant.price }}", "{{ product.default_variant.price|format_currency:product.store.currency_code }}")
        content = content.replace("{{ product.default_variant.discount_price }}", "{{ product.default_variant.discount_price|format_currency:product.store.currency_code }}")
        
    if "product_detail.html" in file_path:
        content = content.replace("{{ object.price }}", "{{ object.price|format_currency:object.store.currency_code }}")
        content = content.replace("{{ object.discount_price }}", "{{ object.discount_price|format_currency:object.store.currency_code }}")
        
    if "product_form.html" in file_path:
        content = content.replace("{{ variant.price }}", "{{ variant.price|format_currency:product.store.currency_code }}")

    with open(full_path, "w") as f:
        f.write(content)
print("Done")
