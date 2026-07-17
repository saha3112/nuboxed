from django.db import models

from apps.common.models import BaseModel


class Role(BaseModel):
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class Permission(BaseModel):
    code = models.CharField(max_length=150, unique=True)
    name = models.CharField(max_length=255)

    def __str__(self) -> str:
        return self.code


class RolePermission(BaseModel):
    role = models.ForeignKey(Role, related_name="role_permissions", on_delete=models.CASCADE)
    permission = models.ForeignKey(
        Permission,
        related_name="permission_roles",
        on_delete=models.CASCADE,
    )

    class Meta:
        unique_together = ("role", "permission")


class UserRole(BaseModel):
    user = models.ForeignKey(
        "users.User",
        related_name="global_roles",
        on_delete=models.CASCADE,
    )
    account_membership = models.ForeignKey(
        "accounts.AccountMembership",
        related_name="user_roles",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    role = models.ForeignKey(Role, related_name="user_roles", on_delete=models.CASCADE)

    class Meta:
        unique_together = ("user", "account_membership", "role")

    def __str__(self) -> str:
        return f"{self.user} / {self.role}"
