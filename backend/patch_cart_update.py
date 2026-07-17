import re

with open('/usr/local/var/www/Nuboxed/backend/apps/storefront/views.py', 'r') as f:
    content = f.read()

old_logic = """        request.session["cart"] = session_cart
        request.session.modified = True
        messages.success(request, "Cart updated.")
        return redirect(request.META.get("HTTP_REFERER", reverse("storefront:cart")))"""

new_logic = """        request.session["cart"] = session_cart
        request.session.modified = True
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True, "quantity": quantity, "cart_count": sum(item["quantity"] for item in session_cart.values())})
        messages.success(request, "Cart updated.")
        return redirect(request.META.get("HTTP_REFERER", reverse("storefront:cart")))"""

content = content.replace(old_logic, new_logic)

# Also update RemoveFromCartView for AJAX support!
old_remove = """        if cart_session_key(cart_item.product, cart_item.variant) in session_cart:
            del session_cart[cart_session_key(cart_item.product, cart_item.variant)]
        request.session["cart"] = session_cart
        request.session.modified = True
        cart_item.delete()
        messages.success(request, "Removed from cart.")
        return redirect(request.META.get("HTTP_REFERER", reverse("storefront:cart")))"""

new_remove = """        if cart_session_key(cart_item.product, cart_item.variant) in session_cart:
            del session_cart[cart_session_key(cart_item.product, cart_item.variant)]
        request.session["cart"] = session_cart
        request.session.modified = True
        cart_item.delete()
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True, "cart_count": sum(item["quantity"] for item in session_cart.values())})
        messages.success(request, "Removed from cart.")
        return redirect(request.META.get("HTTP_REFERER", reverse("storefront:cart")))"""

content = content.replace(old_remove, new_remove)

with open('/usr/local/var/www/Nuboxed/backend/apps/storefront/views.py', 'w') as f:
    f.write(content)
print("Patched cart update/remove")
