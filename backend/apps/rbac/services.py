from apps.accounts.models import AccountMembership
from apps.rbac.constants import DEFAULT_PERMISSIONS, DEFAULT_ROLES, ROLE_CUSTOMER, ROLE_PERMISSION_MAP
from apps.rbac.models import Permission, Role, RolePermission, UserRole


def seed_system_roles():
    permission_map = {}
    for code, name in DEFAULT_PERMISSIONS.items():
        permission, _ = Permission.objects.get_or_create(code=code, defaults={"name": name})
        permission_map[code] = permission

    role_map = {}
    for code, name in DEFAULT_ROLES.items():
        role, _ = Role.objects.get_or_create(code=code, defaults={"name": name})
        role_map[code] = role

    for role_code, permission_codes in ROLE_PERMISSION_MAP.items():
        role = role_map[role_code]
        for permission_code in permission_codes:
            RolePermission.objects.get_or_create(role=role, permission=permission_map[permission_code])

    return role_map


def assign_customer_role(user):
    role_map = seed_system_roles()
    UserRole.objects.get_or_create(user=user, account_membership=None, role=role_map[ROLE_CUSTOMER])


def assign_membership_role(user, membership: AccountMembership, role_code: str):
    role_map = seed_system_roles()
    return UserRole.objects.get_or_create(
        user=user,
        account_membership=membership,
        role=role_map[role_code],
    )
