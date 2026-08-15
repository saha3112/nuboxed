from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import models
from apps.marketplace.models import MarketplaceSyncJob, MarketplaceWebhookEvent
from apps.marketplace.services import process_sync_job, process_webhook_event, cron_fallback_sync

class Command(BaseCommand):
    help = 'Processes pending marketplace sync jobs and webhook events'

    def handle(self, *args, **kwargs):
        stale_before = timezone.now() - timezone.timedelta(minutes=15)
        MarketplaceSyncJob.objects.filter(
            status=MarketplaceSyncJob.STATUS_PROCESSING,
            updated_at__lt=stale_before,
        ).update(status=MarketplaceSyncJob.STATUS_PENDING, run_at=timezone.now(), updated_at=timezone.now())

        # Process Webhooks
        pending_webhooks = MarketplaceWebhookEvent.objects.filter(status=MarketplaceWebhookEvent.STATUS_PENDING)
        webhook_count = pending_webhooks.count()
        self.stdout.write(f"Found {webhook_count} pending webhook events.")
        
        for webhook in list(pending_webhooks):
            process_webhook_event(webhook)

        # Enqueue fallback sync jobs
        enqueued_fallback_jobs = cron_fallback_sync()
        self.stdout.write(f"Enqueued {len(enqueued_fallback_jobs)} fallback sync jobs.")

        # Process Sync Jobs (Pending or Failed but ready for retry)
        ready_jobs = MarketplaceSyncJob.objects.filter(
            models.Q(status=MarketplaceSyncJob.STATUS_PENDING) | 
            models.Q(status=MarketplaceSyncJob.STATUS_FAILED, retry_count__lt=models.F('max_retries')),
            run_at__lte=timezone.now()
        )
        job_count = ready_jobs.count()
        self.stdout.write(f"Found {job_count} ready sync jobs.")

        for job in list(ready_jobs):
            process_sync_job(job)

        self.stdout.write(self.style.SUCCESS('Successfully processed marketplace jobs.'))
