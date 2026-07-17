import re

with open('/usr/local/var/www/Nuboxed/backend/apps/storefront/views.py', 'r') as f:
    content = f.read()

# 1. Patch AddToCompareView
old_compare = """class AddToCompareView(View):
    def post(self, request, product_id, *args, **kwargs):
        compare_list = request.session.get("compare_list", [])
        if str(product_id) not in compare_list:
            if len(compare_list) >= 4:
                messages.warning(request, "You can compare up to 4 products at a time.")
            else:
                compare_list.append(str(product_id))
                request.session["compare_list"] = compare_list
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return JsonResponse({"success": True, "compare_count": len(compare_list), "message": "Product added to compare."})
                messages.success(request, "Product added to compare.")
                
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "message": "Could not add to compare (limit reached or already added)."})
        return redirect(request.META.get("HTTP_REFERER", "storefront:home"))"""

new_compare = """class AddToCompareView(View):
    def post(self, request, product_id, *args, **kwargs):
        compare_list = request.session.get("compare_list", [])
        pid = str(product_id)
        added = False
        msg = ""
        success = True
        
        if pid in compare_list:
            compare_list.remove(pid)
            msg = "Product removed from compare."
        else:
            if len(compare_list) >= 4:
                msg = "You can compare up to 4 products at a time."
                success = False
            else:
                compare_list.append(pid)
                added = True
                msg = "Product added to compare."
                
        if success:
            request.session["compare_list"] = compare_list
            request.session.modified = True
            
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": success, "added": added, "compare_count": len(compare_list), "message": msg})
            
        if success:
            messages.success(request, msg)
        else:
            messages.warning(request, msg)
        return redirect(request.META.get("HTTP_REFERER", "storefront:home"))"""

content = content.replace(old_compare, new_compare)

# 2. Patch AddToCartView ValueError handling
old_cart_err = """        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(request.META.get("HTTP_REFERER", reverse("storefront:cart")))"""

new_cart_err = """        except ValueError as exc:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "message": str(exc)})
            messages.error(request, str(exc))
            return redirect(request.META.get("HTTP_REFERER", reverse("storefront:cart")))"""

content = content.replace(old_cart_err, new_cart_err)

with open('/usr/local/var/www/Nuboxed/backend/apps/storefront/views.py', 'w') as f:
    f.write(content)

print("Views patched.")
