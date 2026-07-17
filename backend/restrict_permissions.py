import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.users.models import User
from django.contrib.auth.models import Permission

retailer = User.objects.get(email='retailer@nuboxed.com')

# Clear all current permissions
retailer.user_permissions.clear()

# List of apps a retailer is allowed to access
allowed_apps = [
    'catalog',
    'inventory',
    'orders',
    'returns_app',
    'shipments',
    'retailers',
    'reports',
    'campaigns',
    'payments',
    'stores'
]

# Fetch permissions only for those apps
perms = Permission.objects.filter(content_type__app_label__in=allowed_apps)
retailer.user_permissions.set(perms)
retailer.save()

print("Restricted permissions to retailer scope only.")
