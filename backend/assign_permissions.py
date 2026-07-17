import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.users.models import User
from django.contrib.auth.models import Permission

retailer = User.objects.get(email='retailer@nuboxed.com')

# Assign all available permissions so they can see the models in Django Admin
all_perms = Permission.objects.all()
retailer.user_permissions.set(all_perms)
retailer.save()

print("Assigned all permissions to retailer")
