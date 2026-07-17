from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.inventory.services import (
    consume_reserved_stock_for_order,
    consume_reserved_stock_for_order_item,
    mark_return_pending_qc,
    reserve_stock_for_order,
    reserve_stock_for_order_item,
    restore_stock_for_cancelled_order,
    restock_return_after_qc,
)
from apps.orders.models import Order, OrderItem
from apps.returns_app.models import ReturnRequest


@receiver(pre_save, sender=Order)
def remember_previous_order_status(sender, instance, **kwargs):
    if instance.pk:
        instance._previous_status = sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
    else:
        instance._previous_status = None


@receiver(post_save, sender=Order)
def sync_inventory_for_order_status(sender, instance, created, **kwargs):
    previous_status = getattr(instance, "_previous_status", None)
    if instance.status == Order.STATUS_CONFIRMED and instance.stock_deducted_at is None:
        if instance.items.exists():
            if not instance.stock_reservations.exists():
                reserve_stock_for_order(instance)
            consume_reserved_stock_for_order(instance)
    elif instance.status == Order.STATUS_CANCELLED and previous_status != Order.STATUS_CANCELLED:
        if instance.stock_reservations.exists() and instance.stock_restored_at is None:
            restore_stock_for_cancelled_order(instance)


@receiver(post_save, sender=OrderItem)
def sync_inventory_for_confirmed_order_item(sender, instance, created, **kwargs):
    if created and instance.order.status == Order.STATUS_CONFIRMED and instance.order.stock_deducted_at is None:
        if not instance.order.stock_reservations.filter(order_item=instance).exists():
            reserve_stock_for_order_item(instance)
            consume_reserved_stock_for_order_item(instance)


@receiver(pre_save, sender=ReturnRequest)
def remember_previous_return_status(sender, instance, **kwargs):
    if instance.pk:
        instance._previous_status = sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
    else:
        instance._previous_status = None


@receiver(post_save, sender=ReturnRequest)
def sync_inventory_for_return_status(sender, instance, created, **kwargs):
    previous_status = getattr(instance, "_previous_status", None)
    if created:
        mark_return_pending_qc(instance)
    elif instance.status == ReturnRequest.STATUS_QC_APPROVED and previous_status != ReturnRequest.STATUS_QC_APPROVED:
        restock_return_after_qc(instance)
