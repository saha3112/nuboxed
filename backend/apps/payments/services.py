import uuid
from decimal import Decimal
from django.db import models, transaction
from django.utils import timezone
from django.conf import settings
from apps.payments.models import (
    PaymentGateway,
    PaymentTransaction,
    RefundTransaction,
    Invoice,
    InvoiceItem,
    CreditNote,
    DebitNote,
    Wallet,
    WalletTransaction,
    RetailerSettlement,
    PlatformCommission,
    GatewayCharges,
    FinancialAuditLog,
)
from apps.notifications.services import send_notification_event

# Helper function to generate unique sequence numbers
def generate_unique_number(prefix: str) -> str:
    return f"{prefix}-{timezone.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


@transaction.atomic
def log_financial_event(actor, event_type: str, target, amount: Decimal = None, currency: str = None, previous_state: dict = None, new_state: dict = None, description: str = "") -> FinancialAuditLog:
    """
    Creates an immutable financial audit log.
    """
    return FinancialAuditLog.objects.create(
        actor=actor,
        event_type=event_type,
        target_type=target.__class__.__name__,
        target_id=str(target.id),
        amount=amount,
        currency=currency,
        previous_state=previous_state or {},
        new_state=new_state or {},
        description=description,
    )


@transaction.atomic
def get_or_create_wallet(owner, owner_type: str = "retailer", currency: str = "EUR") -> Wallet:
    """
    Retrieves or creates a wallet for a Retailer or Customer User.
    """
    if owner_type == "retailer":
        wallet, created = Wallet.objects.get_or_create(
            retailer=owner,
            defaults={"balance": Decimal("0.00"), "currency": currency, "status": Wallet.STATUS_ACTIVE}
        )
    else:
        wallet, created = Wallet.objects.get_or_create(
            user=owner,
            defaults={"balance": Decimal("0.00"), "currency": currency, "status": Wallet.STATUS_ACTIVE}
        )
    return wallet


@transaction.atomic
def modify_wallet_balance(wallet: Wallet, amount: Decimal, transaction_type: str, reference: str = "", description: str = "", actor=None) -> WalletTransaction:
    """
    Modifies the wallet balance and records a ledger entry.
    Locks the wallet row using select_for_update.
    """
    # Lock the wallet row to prevent race conditions
    locked_wallet = Wallet.objects.select_for_update().get(id=wallet.id)
    
    if locked_wallet.status == Wallet.STATUS_FROZEN:
        raise ValueError("Cannot perform transaction: Wallet is frozen.")
        
    previous_balance = locked_wallet.balance
    previous_state = {"balance": str(previous_balance), "status": locked_wallet.status}
    
    # Update balance
    locked_wallet.balance += amount
    locked_wallet.save(update_fields=["balance", "updated_at"])
    
    new_state = {"balance": str(locked_wallet.balance), "status": locked_wallet.status}
    
    # Create ledger transaction
    wallet_tx = WalletTransaction.objects.create(
        wallet=locked_wallet,
        amount=amount,
        currency=locked_wallet.currency,
        transaction_type=transaction_type,
        status=WalletTransaction.STATUS_COMPLETED,
        reference=reference,
        description=description,
    )
    
    # Audit log
    log_financial_event(
        actor=actor,
        event_type=f"WALLET_{transaction_type.upper()}",
        target=locked_wallet,
        amount=amount,
        currency=locked_wallet.currency,
        previous_state=previous_state,
        new_state=new_state,
        description=f"Wallet balance modified by {amount} {locked_wallet.currency}. Details: {description}"
    )
    
    return wallet_tx


@transaction.atomic
def generate_invoice_for_order(order, actor=None) -> Invoice:
    """
    Generates an Invoice and InvoiceItems for a given Order.
    Handles default VAT/GST based on order properties.
    """
    existing = Invoice.objects.filter(order=order).first()
    if existing:
        return existing
    # Calculate tax parameters
    tax_type = Invoice.TAX_TYPE_VAT
    customer_country = "DE"
    if order.address:
        customer_country = order.address.country_code or "DE"
    
    # Set billing details
    billing_name = order.shipping_full_name or f"{order.customer.first_name} {order.customer.last_name}".strip() or order.customer.email
    billing_address = f"{order.shipping_address_line1}\n{order.shipping_address_line2}\n{order.shipping_city}, {order.shipping_state} - {order.shipping_postal_code}, {order.shipping_country_code}".strip()
    
    # Retailer VAT/GST info
    retailer_tax_id = order.retailer.vat_number
    
    invoice = Invoice.objects.create(
        invoice_number=generate_unique_number("INV"),
        order=order,
        customer=order.customer,
        retailer=order.retailer,
        status=Invoice.STATUS_SENT,
        issue_date=timezone.now().date(),
        due_date=timezone.now().date() + timezone.timedelta(days=14),
        currency=order.currency_code,
        subtotal_amount=order.subtotal_amount,
        discount_amount=order.discount_amount,
        tax_amount=order.tax_amount,
        total_amount=order.total_amount,
        tax_type=tax_type,
        billing_name=billing_name,
        billing_address=billing_address,
        customer_tax_id=None,  # Standard customer, can be updated later
        retailer_tax_id=retailer_tax_id,
    )
    
    # Generate line items from Order Items
    for item in order.items.all():
        InvoiceItem.objects.create(
            invoice=invoice,
            product_name=item.product.name,
            product_sku=item.variant.sku if item.variant else item.product.sku,
            quantity=item.quantity,
            unit_price=item.unit_price,
            discount_amount=item.discount_price,
            tax_rate=item.tax_rate,
            tax_amount=item.tax_amount,
            line_total=item.line_total,
        )
        
    log_financial_event(
        actor=actor,
        event_type="INVOICE_GENERATED",
        target=invoice,
        amount=invoice.total_amount,
        currency=invoice.currency,
        previous_state={},
        new_state={"invoice_number": invoice.invoice_number, "status": invoice.status},
        description=f"Invoice generated for order {order.number} with amount {invoice.total_amount} {invoice.currency}"
    )
    
    return invoice


@transaction.atomic
def record_payment_transaction(order, gateway: PaymentGateway, amount: Decimal, currency: str, status: str, gateway_transaction_id: str = None, gateway_response: dict = None, actor=None) -> PaymentTransaction:
    """
    Creates a PaymentTransaction, updating the Order status on success.
    Also triggers commission calculation, wallet deposits, and invoice creation on capture.
    """
    tx = PaymentTransaction.objects.create(
        transaction_number=generate_unique_number("TXN"),
        order=order,
        gateway=gateway,
        amount=amount,
        currency=currency,
        status=status,
        gateway_transaction_id=gateway_transaction_id,
        gateway_response=gateway_response or {},
    )
    
    # Audit log
    log_financial_event(
        actor=actor,
        event_type=f"PAYMENT_{status.upper()}",
        target=tx,
        amount=amount,
        currency=currency,
        previous_state={},
        new_state={"status": status, "gateway_transaction_id": gateway_transaction_id},
        description=f"Payment transaction recorded with status: {status} for order: {order.number}"
    )

    if status == PaymentTransaction.STATUS_CAPTURED:
        # Mark payment transaction captured time
        tx.captured_at = timezone.now()
        tx.save(update_fields=["captured_at", "updated_at"])

        # 1. Update order payment status
        order.payment_status = "paid"
        order.save(update_fields=["payment_status", "updated_at"])
        
        # 2. Record gateway charges (default 2.5% + 0.30 fixed for simulation, or parse from response)
        fee = Decimal("0.00")
        if gateway.code == "stripe":
            fee = ((amount * Decimal("0.029")) + Decimal("0.30")).quantize(Decimal("0.01"))
        elif gateway.code == "paypal":
            fee = ((amount * Decimal("0.034")) + Decimal("0.35")).quantize(Decimal("0.01"))
        elif gateway.code == "razorpay":
            fee = (amount * Decimal("0.020")).quantize(Decimal("0.01"))
        # record
        if fee > 0:
            GatewayCharges.objects.create(
                payment_transaction=tx,
                gateway_code=gateway.code,
                charge_amount=fee,
                currency=currency,
                gateway_fee_details={"calculated": True}
            )

        # 3. Create platform commission
        commission_rate = Decimal("10.00")  # default 10% platform commission
        commission_amount = (amount * (commission_rate / 100)).quantize(Decimal("0.01"))
        
        # 4. Generate Invoice automatically
        invoice = generate_invoice_for_order(order, actor=actor)
        invoice.status = Invoice.STATUS_PAID
        invoice.save(update_fields=["status", "updated_at"])
        
        commission = PlatformCommission.objects.create(
            order=order,
            invoice=invoice,
            retailer=order.retailer,
            gross_amount=amount,
            commission_rate=commission_rate,
            commission_amount=commission_amount,
            currency=currency,
            status=PlatformCommission.STATUS_EARNED
        )

        # 5. Credit Retailer Wallet with net sales (Amount - Commission - Gateway charges)
        net_retailer_credit = (amount - commission_amount - fee).quantize(Decimal("0.01"))
        retailer_wallet = get_or_create_wallet(order.retailer, "retailer", currency=currency)
        modify_wallet_balance(
            wallet=retailer_wallet,
            amount=net_retailer_credit,
            transaction_type=WalletTransaction.TYPE_DEPOSIT,
            reference=f"order_{order.id}",
            description=f"Payout share for Order {order.number} (Gross: {amount}, Comm: {commission_amount}, Gateway: {fee})",
            actor=actor
        )
        
        send_notification_event(
            event_name="payment_received",
            context={"order_number": order.number, "amount": str(amount)},
            user=order.customer
        )
        
    return tx


@transaction.atomic
def process_refund(payment_transaction: PaymentTransaction, amount: Decimal, reason: str, actor=None) -> RefundTransaction:
    """
    Creates a RefundTransaction, deducts refunded amount from Retailer's wallet,
    creates a CreditNote, and updates statuses.
    """
    if payment_transaction.status != PaymentTransaction.STATUS_CAPTURED:
        raise ValueError("Only captured transactions can be refunded.")

    # Calculate already refunded amount
    total_refunded = RefundTransaction.objects.filter(
        payment_transaction=payment_transaction,
        status=RefundTransaction.STATUS_COMPLETED
    ).aggregate(models.Sum('amount'))['amount__sum'] or Decimal("0.00")

    if total_refunded + amount > payment_transaction.amount:
        raise ValueError(f"Refund amount ({amount}) exceeds remaining capturable amount ({payment_transaction.amount - total_refunded}).")

    # Create refund record
    refund = RefundTransaction.objects.create(
        refund_number=generate_unique_number("REF"),
        payment_transaction=payment_transaction,
        amount=amount,
        currency=payment_transaction.currency,
        status=RefundTransaction.STATUS_COMPLETED,
        reason=reason,
    )

    # 1. Update payment transaction status to refunded or partially_refunded
    if total_refunded + amount == payment_transaction.amount:
        payment_transaction.status = PaymentTransaction.STATUS_REFUNDED
    else:
        # Keep captured but support refund tracking
        pass
    payment_transaction.save(update_fields=["status", "updated_at"])

    # 2. Reclaim money from retailer wallet (amount + commission reversal + gateway fee adjustments if applicable)
    # Simple model: retailer wallet is charged the refunded net share
    commission_rate = Decimal("10.00")
    commission_reclaimed = (amount * (commission_rate / 100)).quantize(Decimal("0.01"))
    
    # Calculate gateway fee reversal (usually payment gateways don't refund fees, but let's assume they don't,
    # so we deduct gross refund minus platform commission from retailer wallet)
    retailer_wallet_deduction = (amount - commission_reclaimed).quantize(Decimal("0.01"))
    
    retailer_wallet = get_or_create_wallet(payment_transaction.order.retailer, "retailer", currency=payment_transaction.currency)
    modify_wallet_balance(
        wallet=retailer_wallet,
        amount=-retailer_wallet_deduction,
        transaction_type=WalletTransaction.TYPE_REFUND,
        reference=f"refund_{refund.id}",
        description=f"Refund reclaim for Order {payment_transaction.order.number} (Gross refunded: {amount})",
        actor=actor
    )

    # 3. Create Credit Note for Customer Invoice
    invoice = Invoice.objects.filter(order=payment_transaction.order).first()
    if invoice:
        CreditNote.objects.create(
            credit_note_number=generate_unique_number("CN"),
            invoice=invoice,
            amount=amount,
            currency=payment_transaction.currency,
            status=CreditNote.STATUS_ISSUED,
            reason=reason,
            issued_by=actor,
        )

    log_financial_event(
        actor=actor,
        event_type="REFUND_COMPLETED",
        target=refund,
        amount=amount,
        currency=payment_transaction.currency,
        previous_state={},
        new_state={"status": refund.status},
        description=f"Refund of {amount} {payment_transaction.currency} completed for order {payment_transaction.order.number}"
    )

    return refund


@transaction.atomic
def create_credit_note(invoice: Invoice, amount: Decimal, reason: str, actor=None) -> CreditNote:
    cn = CreditNote.objects.create(
        credit_note_number=generate_unique_number("CN"),
        invoice=invoice,
        amount=amount,
        currency=invoice.currency,
        status=CreditNote.STATUS_ISSUED,
        reason=reason,
        issued_by=actor,
    )
    log_financial_event(
        actor=actor,
        event_type="CREDIT_NOTE_ISSUED",
        target=cn,
        amount=amount,
        currency=invoice.currency,
        description=f"Credit note {cn.credit_note_number} issued for invoice {invoice.invoice_number}"
    )
    return cn


@transaction.atomic
def create_debit_note(invoice: Invoice, amount: Decimal, reason: str, actor=None) -> DebitNote:
    dn = DebitNote.objects.create(
        debit_note_number=generate_unique_number("DN"),
        invoice=invoice,
        amount=amount,
        currency=invoice.currency,
        status=DebitNote.STATUS_ISSUED,
        reason=reason,
        issued_by=actor,
    )
    log_financial_event(
        actor=actor,
        event_type="DEBIT_NOTE_ISSUED",
        target=dn,
        amount=amount,
        currency=invoice.currency,
        description=f"Debit note {dn.debit_note_number} issued for invoice {invoice.invoice_number}"
    )
    return dn


@transaction.atomic
def process_retailer_settlement(retailer, amount: Decimal, currency: str, bank_details: dict, actor=None) -> RetailerSettlement:
    """
    Creates a RetailerSettlement record, deducts balance from Retailer's wallet.
    Initializes payout.
    """
    wallet = get_or_create_wallet(retailer, "retailer", currency=currency)
    if wallet.balance < amount:
        raise ValueError(f"Insufficient wallet balance ({wallet.balance} {currency}) for settlement of {amount} {currency}.")

    settlement = RetailerSettlement.objects.create(
        settlement_number=generate_unique_number("SET"),
        retailer=retailer,
        gross_amount=amount,
        commission_amount=Decimal("0.00"),  # Commission already deducted at sale
        gateway_charges_amount=Decimal("0.00"),  # Gateway charges already deducted at sale
        net_amount=amount,
        currency=currency,
        status=RetailerSettlement.STATUS_PENDING,
        bank_details=bank_details,
    )

    # Deduct wallet balance
    modify_wallet_balance(
        wallet=wallet,
        amount=-amount,
        transaction_type=WalletTransaction.TYPE_SETTLEMENT,
        reference=f"settlement_{settlement.id}",
        description=f"Settlement withdrawal of {amount} {currency}",
        actor=actor
    )

    log_financial_event(
        actor=actor,
        event_type="SETTLEMENT_INITIATED",
        target=settlement,
        amount=amount,
        currency=currency,
        new_state={"status": settlement.status},
        description=f"Settlement payout of {amount} {currency} initiated for retailer {retailer.legal_name}"
    )

    return settlement


@transaction.atomic
def complete_retailer_settlement(settlement: RetailerSettlement, payout_reference: str, actor=None) -> RetailerSettlement:
    """
    Marks a RetailerSettlement as completed.
    """
    previous_state = {"status": settlement.status}
    settlement.status = RetailerSettlement.STATUS_COMPLETED
    settlement.payout_reference = payout_reference
    settlement.paid_at = timezone.now()
    settlement.save(update_fields=["status", "payout_reference", "paid_at", "updated_at"])

    log_financial_event(
        actor=actor,
        event_type="SETTLEMENT_COMPLETED",
        target=settlement,
        amount=settlement.net_amount,
        currency=settlement.currency,
        previous_state=previous_state,
        new_state={"status": settlement.status, "payout_reference": payout_reference},
        description=f"Settlement payout {settlement.settlement_number} completed. Payout reference: {payout_reference}"
    )

    return settlement
