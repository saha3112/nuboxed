import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.users.models import User

# Super Admin
admin, created = User.objects.get_or_create(username='admin', email='admin@nuboxed.com')
admin.set_password('Admin@123')
admin.is_superuser = True
admin.is_staff = True
admin.save()
print(f"Admin {'created' if created else 'updated'}: admin@nuboxed.com / Admin@123")

# Retailer User
retailer, created = User.objects.get_or_create(username='retailer', email='retailer@nuboxed.com')
retailer.set_password('Retailer@123')
retailer.save()
print(f"Retailer {'created' if created else 'updated'}: retailer@nuboxed.com / Retailer@123")
