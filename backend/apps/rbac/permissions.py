from rest_framework.permissions import BasePermission


class CommerceAccessPermission(BasePermission):
    """
    Default DRF permission:
    - authentication is required unless the view explicitly allows anonymous access
    - super admins bypass permission checks
    - views can declare `required_permissions`
    - views can expose `get_permission_account(request)` for retailer scoping
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_super_admin:
            return True

        required_permissions = getattr(view, "required_permissions", [])
        if not required_permissions:
            return True

        account = None
        if hasattr(view, "get_permission_account"):
            account = view.get_permission_account(request)

        return all(
            request.user.has_api_permission(permission_code, account=account)
            for permission_code in required_permissions
        )


class IsSelfOrSuperAdmin(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.is_super_admin or obj == request.user


class IsCustomerOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.is_super_admin or getattr(obj, "customer_id", None) == request.user.id


class IsRetailerAccountMember(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_super_admin:
            return True
        if not hasattr(view, "get_permission_account"):
            return False
        account_id = view.get_permission_account(request)
        if not account_id:
            return False
        return request.user.can_access_account(account_id)
