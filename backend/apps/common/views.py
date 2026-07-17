from django.contrib import messages
from django.shortcuts import redirect
from django.views.csrf import csrf_failure as default_csrf_failure


def csrf_failure(request, reason=""):
    if request.path in {"/admin/login/", "/retailer/login/"}:
        messages.warning(request, "Your login session expired. Please try again.")
        return redirect(request.path)
    return default_csrf_failure(request, reason=reason)
