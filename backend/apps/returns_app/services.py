import uuid
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.conf import settings

from apps.returns_app.models import ReturnRequest, ReturnItem, ReturnTimeline
from apps.orders.models import Order, OrderItem
from apps.payments.services import process_refund
from apps.payments.models import PaymentTransaction
from apps.inventory.services import manual_stock_adjustment
from apps.inventory.models import StockAdjustment, Warehouse
from apps.notifications.models import Notification
from apps.notifications.services import send_notification_event
from apps.users.models import User


def return_stakeholder_emails(return_request):
    emails = set(User.objects.filter(is_active=True, is_superuser=True).exclude(email="").values_list("email", flat=True))
    owner = getattr(getattr(return_request.retailer, "account", None), "owner", None)
    if owner and owner.email:
        emails.add(owner.email)
    return list(emails)

def generate_return_number() -> str:
    return f"RET-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def trigger_notification(user, subject: str, body: str):
    """
    Utility helper to trigger staging notifications.
    Creates a Notification record.
    """
    if user:
        Notification.objects.create(
            user=user,
            channel="email",
            subject=subject,
            body=body,
            status="sent"
        )


@transaction.atomic
def add_timeline_entry(return_request: ReturnRequest, status: str, title: str, note: str = "", actor=None) -> ReturnTimeline:
    """
    Adds a return timeline entry.
    """
    return ReturnTimeline.objects.create(
        return_request=return_request,
        status=status,
        title=title,
        note=note,
        actor=actor,
        occurred_at=timezone.now()
    )


@transaction.atomic
def create_return_request(order: Order, items_data: list, reason: str, customer) -> ReturnRequest:
    """
    Initial stage: Customer requests a return.
    Validates items against order items, creates requests, and notifies stakeholders.
    """
    return_request = ReturnRequest.objects.create(
        return_number=generate_return_number(),
        order=order,
        customer=customer,
        retailer=order.retailer,
        status=ReturnRequest.STATUS_REQUESTED,
        reason=reason
    )

    # Process items
    for item_data in items_data:
        order_item = OrderItem.objects.get(id=item_data["order_item_id"], order=order)
        quantity = item_data["quantity"]
        
        # Verify requested quantity doesn't exceed purchased quantity
        if quantity > order_item.quantity:
            raise ValueError(f"Requested quantity ({quantity}) exceeds purchased quantity ({order_item.quantity}) for {order_item.product.name}.")

        ReturnItem.objects.create(
            return_request=return_request,
            order_item=order_item,
            quantity=quantity,
            qc_status="pending"
        )

    # Trigger inventory pending QC updates now that items are created
    from apps.inventory.services import mark_return_pending_qc
    mark_return_pending_qc(return_request)

    # 1. Timeline
    add_timeline_entry(
        return_request=return_request,
        status=ReturnRequest.STATUS_REQUESTED,
        title="Return Requested",
        note=f"Return request initiated by customer. Reason: {reason}",
        actor=customer
    )

    # 2. Notifications
    send_notification_event(
        event_name="return_request",
        context={"return_number": return_request.return_number},
        user=customer,
        extra_recipients=return_stakeholder_emails(return_request),
    )
    
    # To retailer owner
    if order.retailer.account.owner:
        trigger_notification(
            user=order.retailer.account.owner,
            subject=f"New Return Request: {return_request.return_number}",
            body=f"A new return request {return_request.return_number} has been filed for Order {order.number}."
        )

    return return_request


@transaction.atomic
def review_return_request(return_request: ReturnRequest, approved: bool, notes: str = "", reviewer=None) -> ReturnRequest:
    """
    Stage 2: Retailer or Admin reviews the return request.
    Creates timeline and triggers stage notification.
    """
    if return_request.status != ReturnRequest.STATUS_REQUESTED:
        raise ValueError("Return request has already been reviewed.")

    return_request.reviewed_at = timezone.now()
    return_request.reviewed_by = reviewer

    if approved:
        return_request.status = ReturnRequest.STATUS_APPROVED
        title = "Return Approved"
        note = f"Return request approved. Review notes: {notes}"
        
        # Notify customer
        trigger_notification(
            user=return_request.customer,
            subject=f"Return Request Approved: {return_request.return_number}",
            body=f"Your return request {return_request.return_number} has been approved. We will schedule a return pickup shortly."
        )
    else:
        return_request.status = ReturnRequest.STATUS_REJECTED
        return_request.rejection_reason = notes
        title = "Return Rejected"
        note = f"Return request rejected. Reason: {notes}"

        # Notify customer
        trigger_notification(
            user=return_request.customer,
            subject=f"Return Request Rejected: {return_request.return_number}",
            body=f"Unfortunately, your return request {return_request.return_number} has been rejected. Reason: {notes}"
        )

    return_request.save(update_fields=["status", "rejection_reason", "reviewed_at", "reviewed_by", "updated_at"])

    add_timeline_entry(
        return_request=return_request,
        status=return_request.status,
        title=title,
        note=note,
        actor=reviewer
    )

    return return_request


@transaction.atomic
def schedule_return_pickup(return_request: ReturnRequest, carrier: str, tracking_number: str, date, address: str, actor=None) -> ReturnRequest:
    """
    Stage 3: Return pickup scheduled with courier partner.
    """
    if return_request.status != ReturnRequest.STATUS_APPROVED:
        raise ValueError("Return request must be approved before scheduling pickup.")

    return_request.status = ReturnRequest.STATUS_PICKUP_SCHEDULED
    return_request.pickup_carrier = carrier
    return_request.pickup_tracking_number = tracking_number
    return_request.pickup_date = date
    return_request.pickup_address = address
    return_request.save(update_fields=["status", "pickup_carrier", "pickup_tracking_number", "pickup_date", "pickup_address", "updated_at"])

    add_timeline_entry(
        return_request=return_request,
        status=ReturnRequest.STATUS_PICKUP_SCHEDULED,
        title="Pickup Scheduled",
        note=f"Return pickup scheduled with {carrier}. Tracking: {tracking_number}. Scheduled Date: {date}.",
        actor=actor
    )

    # Notify customer
    trigger_notification(
        user=return_request.customer,
        subject=f"Return Pickup Scheduled: {return_request.return_number}",
        body=f"Your return pickup for request {return_request.return_number} has been scheduled for {date} with {carrier}."
    )

    return return_request


@transaction.atomic
def complete_return_pickup(return_request: ReturnRequest, actor=None) -> ReturnRequest:
    """
    Stage 4: Return pickup completed. Item in transit.
    """
    if return_request.status != ReturnRequest.STATUS_PICKUP_SCHEDULED:
        raise ValueError("Return pickup must be scheduled before it can be completed.")

    return_request.status = ReturnRequest.STATUS_PICKUP_COMPLETED
    return_request.save(update_fields=["status", "updated_at"])

    add_timeline_entry(
        return_request=return_request,
        status=ReturnRequest.STATUS_PICKUP_COMPLETED,
        title="Pickup Completed",
        note="The return items have been picked up by the carrier and are in transit to the warehouse.",
        actor=actor
    )

    # Notify customer and retailer
    trigger_notification(
        user=return_request.customer,
        subject=f"Return Picked Up: {return_request.return_number}",
        body=f"Your return package {return_request.return_number} has been picked up by the carrier."
    )
    if return_request.retailer.account.owner:
        trigger_notification(
            user=return_request.retailer.account.owner,
            subject=f"Return Package In Transit: {return_request.return_number}",
            body=f"Return package {return_request.return_number} is in transit back to your warehouse."
        )

    return return_request


@transaction.atomic
def receive_at_warehouse(return_request: ReturnRequest, actor=None) -> ReturnRequest:
    """
    Stage 5: Arrived at warehouse, awaiting quality control.
    """
    if return_request.status != ReturnRequest.STATUS_PICKUP_COMPLETED:
        raise ValueError("Return package must be picked up/in-transit before arrival.")

    return_request.status = ReturnRequest.STATUS_QC_PENDING
    return_request.save(update_fields=["status", "updated_at"])

    add_timeline_entry(
        return_request=return_request,
        status=ReturnRequest.STATUS_QC_PENDING,
        title="Received at Warehouse",
        note="Return package received at the warehouse. Quality Control (QC) inspection is pending.",
        actor=actor
    )

    # Notify retailer
    if return_request.retailer.account.owner:
        trigger_notification(
            user=return_request.retailer.account.owner,
            subject=f"Return Package Awaiting QC: {return_request.return_number}",
            body=f"Return package {return_request.return_number} has arrived at the warehouse and is queued for QC inspection."
        )

    return return_request


@transaction.atomic
def perform_qc_assessment(return_request: ReturnRequest, qc_results: list, actor=None) -> ReturnRequest:
    """
    Stage 6: Warehouse Quality Control (QC).
    Updates each item's QC status.
    """
    if return_request.status != ReturnRequest.STATUS_QC_PENDING:
        raise ValueError("Return request must be received at warehouse and pending QC.")

    overall_passed = True
    for qc_res in qc_results:
        item = ReturnItem.objects.get(id=qc_res["return_item_id"], return_request=return_request)
        item.qc_status = qc_res["qc_status"]  # passed / failed
        item.qc_note = qc_res.get("qc_note", "")
        item.save(update_fields=["qc_status", "qc_note", "updated_at"])
        
        if qc_res["qc_status"] == "failed":
            overall_passed = False

    return_request.status = ReturnRequest.STATUS_QC_PASSED if overall_passed else ReturnRequest.STATUS_QC_FAILED
    return_request.save(update_fields=["status", "updated_at"])

    status_str = "Passed" if overall_passed else "Failed"
    add_timeline_entry(
        return_request=return_request,
        status=return_request.status,
        title=f"QC Inspection {status_str}",
        note=f"Warehouse quality control check completed with status: {status_str}.",
        actor=actor
    )

    # Notify customer and retailer
    trigger_notification(
        user=return_request.customer,
        subject=f"Return QC Inspection {status_str}: {return_request.return_number}",
        body=f"Your return items for request {return_request.return_number} have completed quality control with status: {status_str}."
    )

    return return_request


@transaction.atomic
def execute_restock_decision(return_request: ReturnRequest, restock_decisions: list, actor=None) -> ReturnRequest:
    """
    Stage 7: Restock decision.
    Rule: Stock restores only after QC approval.
    Increases available inventory for items marked as restocked and QC passed.
    """
    if return_request.status not in [ReturnRequest.STATUS_QC_PASSED, ReturnRequest.STATUS_QC_FAILED]:
        raise ValueError("Cannot perform restock decision until QC assessment is complete.")

    for decision in restock_decisions:
        item = ReturnItem.objects.get(id=decision["return_item_id"], return_request=return_request)
        
        item.restock_decision = decision["restock_decision"]  # restocked / discarded / outlet
        item.restocked_at = timezone.now()
        item.save(update_fields=["restock_decision", "restocked_at", "updated_at"])

        # Rule: Stock restores only if restock_decision is restocked AND qc_status is passed
        if item.restock_decision == ReturnItem.DECISION_RESTOCKED and item.qc_status == "passed":
            # Resolve warehouse: default to item warehouse, or default warehouse of retailer
            warehouse = item.order_item.warehouse or Warehouse.objects.filter(retailer=return_request.retailer, is_default=True).first()
            if not warehouse:
                raise ValueError(f"No warehouse found to restock {item.order_item.product.name}.")

            # Update stock in inventory
            manual_stock_adjustment(
                warehouse=warehouse,
                product=item.order_item.product,
                variant=item.order_item.variant,
                quantity=item.quantity,
                adjustment_type=StockAdjustment.TYPE_INCREASE,
                note=f"Restocked via Return {return_request.return_number}",
                actor=actor
            )

    add_timeline_entry(
        return_request=return_request,
        status="restocked",
        title="Restock Decision Executed",
        note="Restock decisions applied. Eligible items successfully added back to inventory.",
        actor=actor
    )

    return return_request


@transaction.atomic
def approve_refund_amount(return_request: ReturnRequest, refund_amount: Decimal, actor=None) -> ReturnRequest:
    """
    Stage 8: Refund approval.
    Ensures refund amount is valid (can be full or partial).
    """
    # Verify refund amount doesn't exceed captured payments
    txs = PaymentTransaction.objects.filter(order=return_request.order, status=PaymentTransaction.STATUS_CAPTURED)
    if not txs.exists():
        raise ValueError("No captured payment transaction found to refund against.")

    total_captured = sum(tx.amount for tx in txs)
    if refund_amount > total_captured:
        raise ValueError(f"Refund amount ({refund_amount}) exceeds total captured payment amount ({total_captured}).")

    return_request.refund_amount = refund_amount
    return_request.status = ReturnRequest.STATUS_REFUND_APPROVED
    return_request.save(update_fields=["refund_amount", "status", "updated_at"])

    add_timeline_entry(
        return_request=return_request,
        status=ReturnRequest.STATUS_REFUND_APPROVED,
        title="Refund Approved",
        note=f"Refund of {refund_amount} approved. Ready for processing.",
        actor=actor
    )

    # Notify customer
    trigger_notification(
        user=return_request.customer,
        subject=f"Refund Approved: {return_request.return_number}",
        body=f"Your refund of {refund_amount} EUR for return request {return_request.return_number} has been approved."
    )

    return return_request


@transaction.atomic
def process_and_complete_refund(return_request: ReturnRequest, actor=None) -> ReturnRequest:
    """
    Stage 9: Refund processing and completion.
    Links with the Payments module to issue the gateway refund, reclaim commission,
    debit retailer wallet, and generate Credit Note.
    """
    if return_request.status != ReturnRequest.STATUS_REFUND_APPROVED:
        raise ValueError("Refund must be approved before processing.")

    tx = PaymentTransaction.objects.filter(order=return_request.order, status=PaymentTransaction.STATUS_CAPTURED).first()
    if not tx:
        raise ValueError("No active captured transaction to process refund.")

    # Call payments app refund service to process the actual financial refund
    process_refund(
        payment_transaction=tx,
        amount=return_request.refund_amount,
        reason=f"Refund for Return {return_request.return_number}",
        actor=actor
    )

    return_request.status = ReturnRequest.STATUS_COMPLETED
    return_request.save(update_fields=["status", "updated_at"])

    add_timeline_entry(
        return_request=return_request,
        status=ReturnRequest.STATUS_COMPLETED,
        title="Refund Processed & Completed",
        note=f"Financial refund of {return_request.refund_amount} EUR has been processed. Return request closed.",
        actor=actor
    )

    # Notify customer
    send_notification_event(
        event_name="refund_update",
        context={"amount": str(return_request.refund_amount), "return_number": return_request.return_number},
        user=return_request.customer,
        extra_recipients=return_stakeholder_emails(return_request),
    )

    return return_request
