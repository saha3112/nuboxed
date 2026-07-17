from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User, UserSecurityCode
from apps.users.services import issue_security_code, register_user


class UserSummarySerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    account_ids = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "phone",
            "is_email_verified",
            "otp_enabled",
            "roles",
            "account_ids",
        )

    def get_roles(self, obj):
        return list(obj.global_roles.filter(is_active=True).values_list("role__code", flat=True))

    def get_account_ids(self, obj):
        return obj.get_accessible_account_ids()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "username",
            "password",
            "first_name",
            "last_name",
            "phone",
        )

    def create(self, validated_data):
        return register_user(validated_data)


class CommerceTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = User.EMAIL_FIELD

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        token["is_super_admin"] = user.is_super_admin
        token["account_ids"] = user.get_accessible_account_ids()
        return token

    def validate(self, attrs):
        credentials = {
            "email": attrs.get("email"),
            "password": attrs.get("password"),
        }
        user = authenticate(**credentials)
        if user is None:
            raise serializers.ValidationError("Invalid credentials.")
        refresh = self.get_token(user)
        data = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }
        self.user = user
        data["user"] = UserSummarySerializer(self.user).data
        return data


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def save(self, **kwargs):
        token = RefreshToken(self.validated_data["refresh"])
        token.blacklist()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def save(self):
        user = User.objects.filter(email=self.validated_data["email"]).first()
        if user:
            code_record = issue_security_code(user, UserSecurityCode.PURPOSE_PASSWORD_RESET)
            return code_record.code if settings.DEBUG else None
        return None


class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = User.objects.filter(email=attrs["email"]).first()
        if not user:
            raise serializers.ValidationError("Invalid reset request.")
        code_record = (
            UserSecurityCode.objects.filter(
                user=user,
                purpose=UserSecurityCode.PURPOSE_PASSWORD_RESET,
                consumed_at__isnull=True,
            )
            .order_by("-created_at")
            .first()
        )
        if not code_record or not code_record.is_valid(attrs["code"]):
            raise serializers.ValidationError("Invalid or expired reset code.")
        validate_password(attrs["password"], user=user)
        attrs["user"] = user
        attrs["code_record"] = code_record
        return attrs

    def save(self):
        user = self.validated_data["user"]
        code_record = self.validated_data["code_record"]
        user.set_password(self.validated_data["password"])
        user.save(update_fields=["password"])
        code_record.mark_consumed()
        return user


class EmailVerificationRequestSerializer(serializers.Serializer):
    def save(self, user):
        code_record = issue_security_code(user, UserSecurityCode.PURPOSE_EMAIL_VERIFICATION)
        return code_record.code if settings.DEBUG else None


class EmailVerificationConfirmSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6)

    def validate(self, attrs):
        user = self.context["request"].user
        code_record = (
            UserSecurityCode.objects.filter(
                user=user,
                purpose=UserSecurityCode.PURPOSE_EMAIL_VERIFICATION,
                consumed_at__isnull=True,
            )
            .order_by("-created_at")
            .first()
        )
        if not code_record or not code_record.is_valid(attrs["code"]):
            raise serializers.ValidationError("Invalid or expired verification code.")
        attrs["code_record"] = code_record
        return attrs

    def save(self, user):
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])
        self.validated_data["code_record"].mark_consumed()
        return user
