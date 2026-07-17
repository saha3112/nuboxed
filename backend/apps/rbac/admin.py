from django.contrib import admin

from .models import Permission, Role, RolePermission, UserRole


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_system", "is_active")
    search_fields = ("name", "code")


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    search_fields = ("name", "code")


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "permission", "is_active")
    search_fields = ("role__name", "permission__code")


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "account_membership", "is_active")
    search_fields = ("user__email", "role__code", "account_membership__account__name")
