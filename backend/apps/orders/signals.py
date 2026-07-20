from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.orders.models import Order, OrderTimeline


@receiver(pre_save, sender=Order)
def remember_previous_order_status(sender, instance, **kwargs):
    if instance.pk:
        instance._previous_status = sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
    else:
        instance._previous_status = None


@receiver(post_save, sender=Order)
def record_order_timeline_for_status_change(sender, instance, created, **kwargs):
    if created:
        return
    previous_status = getattr(instance, "_previous_status", None)
    if not previous_status or previous_status == instance.status:
        return
    if instance.timeline_entries.filter(status=instance.status).order_by("-occurred_at").first():
        latest = instance.timeline_entries.filter(status=instance.status).order_by("-occurred_at").first()
        if latest and latest.title.lower().startswith(instance.status.replace("_", " ")):
            return
    OrderTimeline.objects.create(
        order=instance,
        status=instance.status,
        title=f"Order {instance.get_status_display()}",
        note=getattr(instance, "_timeline_note", "") or f"Order status changed from {previous_status} to {instance.status}.",
        actor=getattr(instance, "_timeline_actor", None),
    )
