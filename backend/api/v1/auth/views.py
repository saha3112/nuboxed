from rest_framework import generics, permissions, response, status
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import (
    CommerceTokenObtainPairSerializer,
    EmailVerificationConfirmSerializer,
    EmailVerificationRequestSerializer,
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSummarySerializer,
)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        response_obj = super().create(request, *args, **kwargs)
        user = self.serializer_class.Meta.model.objects.get(id=response_obj.data["id"])
        serializer = EmailVerificationRequestSerializer(data={})
        serializer.is_valid(raise_exception=True)
        debug_code = serializer.save(user=user)
        if debug_code:
            response_obj.data["email_verification_debug_code"] = debug_code
        return response_obj


class LoginView(TokenObtainPairView):
    serializer_class = CommerceTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]


class RefreshView(TokenRefreshView):
    permission_classes = [permissions.AllowAny]


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return response.Response(UserSummarySerializer(request.user).data)


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        debug_code = serializer.save()
        payload = {"detail": "If the account exists, a reset code has been sent."}
        if debug_code:
            payload["debug_code"] = debug_code
        return response.Response(payload)


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response({"detail": "Password has been reset successfully."})


class EmailVerificationRequestView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = EmailVerificationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        debug_code = serializer.save(user=request.user)
        payload = {"detail": "Verification code sent."}
        if debug_code:
            payload["debug_code"] = debug_code
        return response.Response(payload)


class EmailVerificationConfirmView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = EmailVerificationConfirmSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return response.Response({"detail": "Email verified successfully."})
