from django.core.management.base import BaseCommand

from apps.rbac.services import seed_system_roles


class Command(BaseCommand):
    help = "Seed default CommerceOS roles and permissions."

    def handle(self, *args, **options):
        seed_system_roles()
        self.stdout.write(self.style.SUCCESS("RBAC roles and permissions seeded."))
