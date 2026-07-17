import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.users.models import User

retailer = User.objects.get(email='retailer@nuboxed.com')
retailer.is_staff = True
retailer.save()
print("Retailer is_staff set to True")
