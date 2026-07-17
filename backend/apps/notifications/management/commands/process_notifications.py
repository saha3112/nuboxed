from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.notifications.models import Notification
from apps.notifications.services import dispatch_notification, retry_failed_notifications

class Command(BaseCommand):
    help = 'Processes pending and failed notifications'

    def handle(self, *args, **kwargs):
        # Process pending notifications
        pending = Notification.objects.filter(status=Notification.STATUS_PENDING, run_at__lte=timezone.now())
        pending_count = pending.count()
        self.stdout.write(f"Found {pending_count} pending notifications.")
        
        for notification in list(pending):
            dispatch_notification(notification)

        # Process retries for failed notifications
        retried = retry_failed_notifications()
        self.stdout.write(f"Retried {len(retried)} failed notifications.")

        self.stdout.write(self.style.SUCCESS('Successfully processed notifications.'))
