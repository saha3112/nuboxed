from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class Account(BaseModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="owned_accounts",
        on_delete=models.PROTECT,
    )
    country_code = models.CharField(max_length=2, default="DE")
    currency_code = models.CharField(max_length=3, default="EUR")

    def __str__(self) -> str:
        return self.name


class AccountMembership(BaseModel):
    account = models.ForeignKey(Account, related_name="memberships", on_delete=models.CASCADE)
    store = models.ForeignKey(
        "stores.Store",
        related_name="staff_memberships",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="account_memberships",
        on_delete=models.CASCADE,
    )
    title = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=32, default="active")

    class Meta:
        unique_together = ("account", "user")

    def __str__(self) -> str:
        return f"{self.account} / {self.user}"
