import re

with open('/usr/local/var/www/Nuboxed/backend/apps/storefront/views.py', 'r') as f:
    content = f.read()

# HomePageView
content = re.sub(
    r'active_stores, _, _ = self\.apply_location_filter\(active_stores, location_payload, ignore_location=ignore_location, is_store_qs=True\)',
    r'active_stores, location_msg, location_url = self.apply_location_filter(active_stores, location_payload, ignore_location=ignore_location, is_store_qs=True)',
    content
)
content = re.sub(
    r'"active_stores": active_stores\[:8\],',
    r'"active_stores": active_stores[:8],\n                "location_msg": location_msg,\n                "location_url": location_url,',
    content
)

# ProductListingPageView
old_plist = """        qs = APPROVED_PRODUCT_QS
        qs, _, _ = self.apply_location_filter(qs, location_payload, ignore_location=ignore_location)"""
new_plist = """        qs = APPROVED_PRODUCT_QS
        qs, location_msg, location_url = self.apply_location_filter(qs, location_payload, ignore_location=ignore_location)"""
content = content.replace(old_plist, new_plist)

if '"location_msg"' not in content[content.find("class ProductListingPageView"):content.find("class SellerComparisonPageView")]:
    content = re.sub(
        r'("products": products,\n\s+"page_obj": page_obj,)',
        r'\1\n                "location_msg": location_msg,\n                "location_url": location_url,',
        content,
        count=1
    )

with open('/usr/local/var/www/Nuboxed/backend/apps/storefront/views.py', 'w') as f:
    f.write(content)
print("Patched msg passing in views.")
