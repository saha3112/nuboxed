from django.contrib import admin

from .models import Retailer


@admin.register(Retailer)
class RetailerAdmin(admin.ModelAdmin):
    list_display = ("legal_name", "display_name", "support_email", "status", "is_active")
    search_fields = ("legal_name", "display_name", "support_email", "vat_number")
    list_filter = ("status", "is_active")
