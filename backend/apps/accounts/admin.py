from django.contrib import admin

from .models import Account, AccountMembership


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "country_code", "currency_code", "is_active")
    search_fields = ("name", "slug")


@admin.register(AccountMembership)
class AccountMembershipAdmin(admin.ModelAdmin):
    list_display = ("account", "user", "title", "is_active")
    search_fields = ("account__name", "user__username", "user__email")
