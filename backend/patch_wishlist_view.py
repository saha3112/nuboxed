import re

with open('/usr/local/var/www/Nuboxed/backend/apps/storefront/views.py', 'r') as f:
    content = f.read()

old_view = """class AddToWishlistView(View):
    def post(self, request, product_id):
        product = get_object_or_404(APPROVED_PRODUCT_QS, id=product_id)
        wishlist = request.session.get("wishlist", [])
        if str(product.id) not in wishlist:
            wishlist.append(str(product.id))
        request.session["wishlist"] = wishlist
        request.session.modified = True
        
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True, "wishlist_count": len(wishlist), "message": f"{product.name} added to wishlist."})
            
        messages.success(request, f"{product.name} added to wishlist.")
        return redirect(request.META.get("HTTP_REFERER", reverse("storefront:products")))"""

new_view = """class AddToWishlistView(View):
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
        return redirect(request.META.get("HTTP_REFERER", reverse("storefront:products")))"""

if old_view in content:
    content = content.replace(old_view, new_view)
    with open('/usr/local/var/www/Nuboxed/backend/apps/storefront/views.py', 'w') as f:
        f.write(content)
    print("Successfully patched AddToWishlistView to act as a toggle.")
else:
    print("Could not find AddToWishlistView exactly as defined.")
