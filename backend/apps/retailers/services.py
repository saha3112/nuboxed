from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.models import Account, AccountMembership
from apps.rbac.constants import ROLE_RETAILER_MANAGER, ROLE_RETAILER_OWNER
from apps.rbac.models import UserRole
from apps.rbac.services import assign_membership_role
from apps.retailers.models import Retailer
from apps.stores.models import Store
from apps.notifications.services import send_notification_event
from apps.users.models import User

def unique_slug(model, value, source_field="slug"):
    base = slugify(value) or "store"
    slug = base
    index = 1
    while model.objects.filter(**{source_field: slug}).exists():
        index += 1
        slug = f"{base}-{index}"
    return slug


@transaction.atomic
def register_retailer(owner: User, retailer_data: dict, store_data: dict):
    account_name = retailer_data.get("display_name") or retailer_data["legal_name"]
    account = Account.objects.create(
        name=account_name,
        slug=unique_slug(Account, account_name),
        owner=owner,
        country_code=store_data.get("country_code", "DE"),
    )
    retailer = Retailer.objects.create(
        account=account,
        status=Retailer.STATUS_PENDING,
        **retailer_data,
    )
    store = Store.objects.create(
        retailer=retailer,
        slug=unique_slug(Store, store_data["name"]),
        status=Store.STATUS_DRAFT,
        **store_data,
    )
    membership = AccountMembership.objects.create(
        account=account,
        store=None,
        user=owner,
        title="Retailer Owner",
    )
    assign_membership_role(owner, membership, ROLE_RETAILER_OWNER)
    
    send_notification_event(
        event_name="new_registration",
        context={"email": owner.email},
        user=owner,
        extra_recipients=list(User.objects.filter(is_superuser=True, is_active=True).exclude(email="").values_list("email", flat=True)),
    )
    
    return retailer


@transaction.atomic
def approve_retailer(retailer: Retailer, approver: User, notes=""):
    retailer.status = Retailer.STATUS_APPROVED
    retailer.approved_at = timezone.now()
    retailer.approved_by = approver
    retailer.approval_notes = notes
    retailer.save(update_fields=["status", "approved_at", "approved_by", "approval_notes", "updated_at"])
    retailer.stores.update(status=Store.STATUS_ACTIVE)
    
    send_notification_event(
        event_name="retailer_approval",
        context={"legal_name": retailer.legal_name},
        user=retailer.account.owner if retailer.account else None
    )
    
    return retailer


@transaction.atomic
def add_store_staff(*, account, store, user: User, title: str, role_codes=None, role_code=None):
    role_codes = list(role_codes or ([role_code] if role_code else []))
    membership, _ = AccountMembership.objects.get_or_create(
        account=account,
        user=user,
        defaults={"store": store, "title": title, "status": "active"},
    )
    membership.store = store
    membership.title = title
    membership.status = "active"
    membership.is_active = True
    membership.save(update_fields=["store", "title", "status", "is_active", "updated_at"])

    UserRole.objects.filter(user=user, account_membership=membership).delete()
    for selected_role_code in role_codes:
        assign_membership_role(user, membership, selected_role_code)
    return membership


def retailer_user_store_ids(user: User):
    return list(
        user.account_memberships.filter(is_active=True, store__isnull=False).values_list("store_id", flat=True)
    )
