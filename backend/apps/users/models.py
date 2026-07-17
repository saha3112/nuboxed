import secrets
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel, TimeStampedModel
from .managers import UserManager


class User(AbstractUser, TimeStampedModel):
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=32, blank=True)
    is_email_verified = models.BooleanField(default=False)
    is_phone_verified = models.BooleanField(default=False)
    otp_enabled = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = UserManager()

    def __str__(self) -> str:
        return self.email

    @property
    def is_super_admin(self) -> bool:
        return self.is_superuser or self.global_roles.filter(
            role__code="super_admin",
            account_membership__isnull=True,
        ).exists()

    def get_permission_codes(self, account=None):
        from apps.rbac.models import RolePermission

        filters = {"role__user_roles__user": self, "role__user_roles__is_active": True}
        if account is None:
            filters["role__user_roles__account_membership__isnull"] = True
        else:
            filters["role__user_roles__account_membership__account"] = account

        codes = RolePermission.objects.filter(**filters).values_list("permission__code", flat=True)
        return set(codes)

    def has_api_permission(self, permission_code, account=None) -> bool:
        if self.is_super_admin:
            return True
        return permission_code in self.get_permission_codes(account=account)

    def get_accessible_account_ids(self):
        account_ids = set(
            self.account_memberships.filter(is_active=True, status="active").values_list("account_id", flat=True)
        )
        account_ids.update(self.owned_accounts.values_list("id", flat=True))
        return list(account_ids)

    def can_access_account(self, account_id) -> bool:
        if self.is_super_admin:
            return True
        if self.owned_accounts.filter(id=account_id).exists():
            return True
        return self.account_memberships.filter(account_id=account_id, is_active=True, status="active").exists()

    def get_accessible_store_ids(self, account=None):
        if account is not None and getattr(account, "owner_id", None) == self.id:
            return None
        memberships = self.account_memberships.filter(is_active=True, status="active")
        if account is not None:
            memberships = memberships.filter(account=account)
        if memberships.filter(store__isnull=True).exists():
            return None
        return list(memberships.exclude(store__isnull=True).values_list("store_id", flat=True))

    def can_access_store(self, store) -> bool:
        if self.is_super_admin:
            return True
        store_id = getattr(store, "id", store)
        account = getattr(getattr(store, "retailer", None), "account", None)
        if account and getattr(account, "owner_id", None) == self.id:
            return True
        memberships = self.account_memberships.filter(is_active=True, status="active")
        return memberships.filter(store_id=store_id).exists() or memberships.filter(store__isnull=True).exists()


class UserSecurityCode(BaseModel):
    PURPOSE_EMAIL_VERIFICATION = "email_verification"
    PURPOSE_PASSWORD_RESET = "password_reset"
    PURPOSE_LOGIN_OTP = "login_otp"

    CHANNEL_EMAIL = "email"
    CHANNEL_SMS = "sms"

    PURPOSE_CHOICES = [
        (PURPOSE_EMAIL_VERIFICATION, "Email verification"),
        (PURPOSE_PASSWORD_RESET, "Password reset"),
        (PURPOSE_LOGIN_OTP, "Login OTP"),
    ]
    CHANNEL_CHOICES = [
        (CHANNEL_EMAIL, "Email"),
        (CHANNEL_SMS, "SMS"),
    ]

    user = models.ForeignKey(
        "users.User",
        related_name="security_codes",
        on_delete=models.CASCADE,
    )
    purpose = models.CharField(max_length=32, choices=PURPOSE_CHOICES)
    channel = models.CharField(max_length=16, choices=CHANNEL_CHOICES, default=CHANNEL_EMAIL)
    code = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "purpose", "expires_at"]),
        ]

    @classmethod
    def issue(cls, user, purpose, channel=CHANNEL_EMAIL, ttl_minutes=15):
        code = f"{secrets.randbelow(1000000):06d}"
        return cls.objects.create(
            user=user,
            purpose=purpose,
            channel=channel,
            code=code,
            expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
        )

    def is_valid(self, submitted_code):
        return (
            self.code == submitted_code
            and self.consumed_at is None
            and self.expires_at >= timezone.now()
        )

    def mark_consumed(self):
        self.consumed_at = timezone.now()
        self.save(update_fields=["consumed_at", "updated_at"])


class UserAddress(BaseModel):
    user = models.ForeignKey(
        "users.User",
        related_name="addresses",
        on_delete=models.CASCADE,
    )
    label = models.CharField(max_length=80, default="Home")
    full_name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=32)
    country_code = models.CharField(max_length=2, default="DE")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ("-is_default", "-updated_at")
        indexes = [
            models.Index(fields=["user", "is_default"]),
            models.Index(fields=["postal_code"]),
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            self.user.addresses.exclude(id=self.id).update(is_default=False)

    def __str__(self):
        return f"{self.user.email} / {self.label} / {self.postal_code}"


class GDPRConsent(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="gdpr_consents")
    marketing_accepted = models.BooleanField(default=False)
    analytics_accepted = models.BooleanField(default=False)
    third_party_accepted = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)


class PrivacyRequest(BaseModel):
    TYPE_EXPORT = 'export'
    TYPE_DELETE = 'delete'
    TYPE_CHOICES = [(TYPE_EXPORT, 'Data Export'), (TYPE_DELETE, 'Account Deletion')]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="privacy_requests")
    request_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, default='pending')
    processed_at = models.DateTimeField(null=True, blank=True)
