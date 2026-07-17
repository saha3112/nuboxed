from django.contrib import admin
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User, UserAddress, UserSecurityCode


@admin.register(User)
class CommerceUserAdmin(UserAdmin):
    list_display = ("username", "email", "is_staff", "is_active", "is_email_verified")
    list_filter = ("is_staff", "is_active", "is_email_verified")
    search_fields = ("username", "email", "phone")


@admin.register(UserSecurityCode)
class UserSecurityCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "purpose", "channel", "expires_at", "consumed_at")
    search_fields = ("user__email", "code")


@admin.register(UserAddress)
class UserAddressAdmin(admin.ModelAdmin):
    list_display = ("user", "label", "postal_code", "city", "country_code", "is_default", "is_active")
    list_filter = ("country_code", "is_default", "is_active")
    search_fields = ("user__email", "postal_code", "city", "state")
