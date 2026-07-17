from rest_framework import serializers

from apps.accounts.models import AccountMembership
from apps.rbac.constants import (
    ROLE_FINANCE_MANAGER,
    ROLE_ORDER_MANAGER,
    ROLE_PRODUCT_MANAGER,
    ROLE_REPORT_VIEWER,
    ROLE_RETAILER_MANAGER,
    ROLE_STOCK_MANAGER,
)
from apps.retailers.models import Retailer
from apps.retailers.services import add_store_staff, register_retailer
from apps.stores.models import Store
from apps.users.models import User
from apps.users.services import generate_unique_username, register_user


class RetailerStoreSerializer(serializers.ModelSerializer):
    show_logo = serializers.SerializerMethodField()
    show_banner = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = (
            "id",
            "name",
            "slug",
            "logo",
            "banner",
            "icon",
            "description",
            "contact_email",
            "contact_phone",
            "contact_whatsapp",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
            "country_code",
            "facebook_url",
            "instagram_url",
            "linkedin_url",
            "x_url",
            "youtube_url",
            "website_url",
            "status",
            "show_logo",
            "show_banner",
        )
        read_only_fields = ("slug", "status", "show_logo", "show_banner")

    def get_show_logo(self, obj):
        return bool(obj.logo)

    def get_show_banner(self, obj):
        return bool(obj.banner)


class RetailerProfileSerializer(serializers.ModelSerializer):
    stores = serializers.SerializerMethodField()

    class Meta:
        model = Retailer
        fields = (
            "id",
            "legal_name",
            "display_name",
            "vat_number",
            "registration_number",
            "support_email",
            "support_phone",
            "business_address",
            "description",
            "status",
            "approval_notes",
            "stores",
        )
        read_only_fields = ("status", "approval_notes", "stores")

    def get_stores(self, obj):
        request = self.context.get("request")
        queryset = obj.stores.all()
        if request and request.user.is_authenticated:
            store_ids = request.user.get_accessible_store_ids(account=obj.account)
            if store_ids is not None:
                queryset = queryset.filter(id__in=store_ids)
        return RetailerStoreSerializer(queryset, many=True).data


class RetailerRegistrationSerializer(serializers.Serializer):
    owner_email = serializers.EmailField()
    owner_password = serializers.CharField(write_only=True)
    owner_first_name = serializers.CharField(required=False, allow_blank=True)
    owner_last_name = serializers.CharField(required=False, allow_blank=True)
    owner_phone = serializers.CharField(required=False, allow_blank=True)
    legal_name = serializers.CharField()
    display_name = serializers.CharField(required=False, allow_blank=True)
    vat_number = serializers.CharField(required=False, allow_blank=True)
    registration_number = serializers.CharField(required=False, allow_blank=True)
    support_email = serializers.EmailField(required=False, allow_blank=True)
    support_phone = serializers.CharField(required=False, allow_blank=True)
    business_address = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    store_name = serializers.CharField()
    store_description = serializers.CharField(required=False, allow_blank=True)
    store_contact_email = serializers.EmailField(required=False, allow_blank=True)
    store_contact_phone = serializers.CharField(required=False, allow_blank=True)
    store_contact_whatsapp = serializers.CharField(required=False, allow_blank=True)
    country_code = serializers.CharField(required=False, default="DE")

    def create(self, validated_data):
        owner = register_user(
            {
                "email": validated_data["owner_email"],
                "password": validated_data["owner_password"],
                "first_name": validated_data.get("owner_first_name", ""),
                "last_name": validated_data.get("owner_last_name", ""),
                "phone": validated_data.get("owner_phone", ""),
            }
        )
        retailer_data = {
            "legal_name": validated_data["legal_name"],
            "display_name": validated_data.get("display_name", ""),
            "vat_number": validated_data.get("vat_number", ""),
            "registration_number": validated_data.get("registration_number", ""),
            "support_email": validated_data.get("support_email", ""),
            "support_phone": validated_data.get("support_phone", ""),
            "business_address": validated_data.get("business_address", ""),
            "description": validated_data.get("description", ""),
        }
        store_data = {
            "name": validated_data["store_name"],
            "description": validated_data.get("store_description", ""),
            "contact_email": validated_data.get("store_contact_email", ""),
            "contact_phone": validated_data.get("store_contact_phone", ""),
            "contact_whatsapp": validated_data.get("store_contact_whatsapp", ""),
            "country_code": validated_data.get("country_code", "DE"),
        }
        return register_retailer(owner, retailer_data, store_data)


class StoreUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Store
        exclude = ("retailer", "slug", "created_at", "updated_at")
        read_only_fields = ("status",)


class RetailerApprovalSerializer(serializers.Serializer):
    approval_notes = serializers.CharField(required=False, allow_blank=True)


class StoreStaffSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    role_codes = serializers.SerializerMethodField()

    class Meta:
        model = AccountMembership
        fields = ("id", "email", "title", "status", "store", "role_codes")

    def get_role_codes(self, obj):
        return list(obj.user_roles.filter(is_active=True).values_list("role__code", flat=True))


class StoreStaffCreateSerializer(serializers.Serializer):
    ROLE_CHOICES = [
        ROLE_RETAILER_MANAGER,
        ROLE_PRODUCT_MANAGER,
        ROLE_STOCK_MANAGER,
        ROLE_ORDER_MANAGER,
        ROLE_FINANCE_MANAGER,
        ROLE_REPORT_VIEWER,
    ]

    email = serializers.EmailField()
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    title = serializers.CharField(required=False, allow_blank=True)
    role_code = serializers.ChoiceField(choices=ROLE_CHOICES)
    store_id = serializers.UUIDField()

    def validate(self, attrs):
        retailer = self.context["retailer"]
        try:
            attrs["store"] = retailer.stores.get(id=attrs["store_id"])
        except Store.DoesNotExist as exc:
            raise serializers.ValidationError("Invalid store.") from exc
        return attrs

    def create(self, validated_data):
        user, created = User.objects.get_or_create(
            email=validated_data["email"],
            defaults={
                "username": generate_unique_username(validated_data["email"]),
                "first_name": validated_data.get("first_name", ""),
                "last_name": validated_data.get("last_name", ""),
                "phone": validated_data.get("phone", ""),
            },
        )
        membership = add_store_staff(
            account=self.context["retailer"].account,
            store=validated_data["store"],
            user=user,
            title=validated_data.get("title", validated_data["role_code"].replace("_", " ").title()),
            role_code=validated_data["role_code"],
        )
        return membership
