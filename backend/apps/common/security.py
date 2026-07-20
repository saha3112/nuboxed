import hmac
import hashlib
from functools import wraps
from django.core.exceptions import PermissionDenied
from django.conf import settings
from rest_framework.exceptions import Throttled


def build_public_url(request, path: str) -> str:
    """Build a QR-safe URL, allowing deployments to replace localhost via PUBLIC_APP_URL."""
    configured_base = getattr(settings, "PUBLIC_APP_URL", "")
    if configured_base:
        return f"{configured_base}/{str(path).lstrip('/')}"
    return request.build_absolute_uri(path)

def verify_webhook_signature(payload_body: bytes, signature_header: str, secret: str) -> bool:
    """
    Verifies the webhook signature using HMAC SHA256.
    """
    if not signature_header or not secret:
        return False
        
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature_header)


def require_rbac_permission(permission_code):
    """
    Decorator to enforce RBAC permissions on views.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise PermissionDenied("Authentication required.")
            
            # Fetch account if available in kwargs
            account_id = kwargs.get('account_id')
            
            if not request.user.has_api_permission(permission_code, account=account_id):
                raise PermissionDenied(f"Missing required permission: {permission_code}")
                
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def enforce_2fa(view_func):
    """
    Decorator to ensure the user has completed 2FA for this session.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required.")
        
        # Check session or token for 2FA claim
        if request.user.otp_enabled and not request.session.get('2fa_verified', False):
            raise PermissionDenied("2FA verification required.")
            
        return view_func(request, *args, **kwargs)
    return _wrapped_view
