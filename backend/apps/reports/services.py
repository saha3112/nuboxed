import csv
import io
from decimal import Decimal

from django.db.models import Sum, Count, Q
from django.utils import timezone

from apps.retailers.models import Retailer
from apps.catalog.models import Product, Category
from apps.orders.models import Order, OrderItem
from apps.payments.models import PaymentTransaction, RefundTransaction, RetailerSettlement
from apps.returns_app.models import ReturnRequest
from apps.inventory.models import LowStockAlert, OfflineSale, StockItem
from apps.marketplace.models import MarketplaceConnection, MarketplaceSyncJob
from apps.reports.models import ReportJob


def generate_admin_report(start_date=None, end_date=None):
    """
    Generates a comprehensive admin report.
    Returns a dictionary of aggregated metrics.
    """
    metrics = {}
    
    # 1. Total retailers
    retailers_qs = Retailer.objects.all()
    if start_date: retailers_qs = retailers_qs.filter(created_at__gte=start_date)
    if end_date: retailers_qs = retailers_qs.filter(created_at__lte=end_date)
    metrics["total_retailers"] = retailers_qs.count()

    # 2. Total products
    products_qs = Product.objects.all()
    if start_date: products_qs = products_qs.filter(created_at__gte=start_date)
    if end_date: products_qs = products_qs.filter(created_at__lte=end_date)
    metrics["total_products"] = products_qs.count()

    # 3. Total orders
    orders_qs = Order.objects.all()
    if start_date: orders_qs = orders_qs.filter(created_at__gte=start_date)
    if end_date: orders_qs = orders_qs.filter(created_at__lte=end_date)
    metrics["total_orders"] = orders_qs.count()

    # 4. Sales
    sales_agg = orders_qs.filter(status__in=[Order.STATUS_COMPLETED, Order.STATUS_PROCESSING, Order.STATUS_DELIVERED]).aggregate(total_sales=Sum('total_amount'))
    metrics["sales"] = sales_agg["total_sales"] or Decimal("0.00")

    # 5. Pending payments
    pending_payments_qs = PaymentTransaction.objects.filter(status=PaymentTransaction.STATUS_PENDING)
    if start_date: pending_payments_qs = pending_payments_qs.filter(created_at__gte=start_date)
    if end_date: pending_payments_qs = pending_payments_qs.filter(created_at__lte=end_date)
    pending_agg = pending_payments_qs.aggregate(total_pending=Sum('amount'))
    metrics["pending_payments"] = pending_agg["total_pending"] or Decimal("0.00")

    # 6. Refunds
    refunds_qs = RefundTransaction.objects.filter(status=RefundTransaction.STATUS_COMPLETED)
    if start_date: refunds_qs = refunds_qs.filter(created_at__gte=start_date)
    if end_date: refunds_qs = refunds_qs.filter(created_at__lte=end_date)
    refunds_agg = refunds_qs.aggregate(total_refunds=Sum('amount'))
    metrics["refunds"] = refunds_agg["total_refunds"] or Decimal("0.00")

    # 7. Returns
    returns_qs = ReturnRequest.objects.all()
    if start_date: returns_qs = returns_qs.filter(created_at__gte=start_date)
    if end_date: returns_qs = returns_qs.filter(created_at__lte=end_date)
    metrics["returns"] = returns_qs.count()

    # 8. Top categories
    # Assuming OrderItem links to product which links to category
    top_categories = OrderItem.objects.filter(order__in=orders_qs).values('product__category__name').annotate(
        total_quantity=Sum('quantity'),
        total_sales=Sum('total_amount')
    ).order_by('-total_sales')[:10]
    metrics["top_categories"] = list(top_categories)

    # 9. Top retailers
    top_retailers = orders_qs.values('retailer__name').annotate(
        total_orders=Count('id'),
        total_sales=Sum('total_amount')
    ).order_by('-total_sales')[:10]
    metrics["top_retailers"] = list(top_retailers)

    # 10. Stock alerts
    stock_alerts_qs = LowStockAlert.objects.filter(resolved_at__isnull=True)
    if start_date: stock_alerts_qs = stock_alerts_qs.filter(created_at__gte=start_date)
    if end_date: stock_alerts_qs = stock_alerts_qs.filter(created_at__lte=end_date)
    metrics["stock_alerts"] = stock_alerts_qs.count()

    # 11. Marketplace sync errors
    # Check failed jobs or connections with error status
    sync_errors_qs = MarketplaceSyncJob.objects.filter(status=MarketplaceSyncJob.STATUS_FAILED)
    if start_date: sync_errors_qs = sync_errors_qs.filter(created_at__gte=start_date)
    if end_date: sync_errors_qs = sync_errors_qs.filter(created_at__lte=end_date)
    metrics["marketplace_sync_errors"] = sync_errors_qs.count()

    return metrics


def generate_retailer_report(retailer, start_date=None, end_date=None):
    """
    Generates a report for a specific retailer.
    """
    metrics = {}

    # 1. Total products
    products_qs = Product.objects.filter(retailer=retailer)
    if start_date: products_qs = products_qs.filter(created_at__gte=start_date)
    if end_date: products_qs = products_qs.filter(created_at__lte=end_date)
    metrics["total_products"] = products_qs.count()

    # 2. Total stock
    # Sum of on_hand_quantity for all stock items across retailer's warehouses
    stock_agg = StockItem.objects.filter(warehouse__retailer=retailer).aggregate(total_stock=Sum('on_hand_quantity'))
    metrics["total_stock"] = stock_agg["total_stock"] or 0

    # 3. Online sales
    orders_qs = Order.objects.filter(retailer=retailer)
    if start_date: orders_qs = orders_qs.filter(created_at__gte=start_date)
    if end_date: orders_qs = orders_qs.filter(created_at__lte=end_date)
    online_sales_agg = orders_qs.filter(source_channel=Order.SOURCE_WEBSITE, status__in=[Order.STATUS_COMPLETED, Order.STATUS_PROCESSING, Order.STATUS_DELIVERED]).aggregate(total_sales=Sum('total_amount'))
    metrics["online_sales"] = online_sales_agg["total_sales"] or Decimal("0.00")

    # 4. Offline sales
    offline_qs = OfflineSale.objects.filter(warehouse__retailer=retailer)
    if start_date: offline_qs = offline_qs.filter(created_at__gte=start_date)
    if end_date: offline_qs = offline_qs.filter(created_at__lte=end_date)
    offline_sales_agg = offline_qs.aggregate(total_sales=Sum('total_amount'))
    metrics["offline_sales"] = offline_sales_agg["total_sales"] or Decimal("0.00")
    metrics["offline_sale_records"] = offline_qs.count()
    metrics["offline_sale_type"] = "Offline Sale"

    # 5. Orders
    metrics["total_orders"] = orders_qs.count()

    # 6. Returns
    returns_qs = ReturnRequest.objects.filter(order__retailer=retailer)
    if start_date: returns_qs = returns_qs.filter(created_at__gte=start_date)
    if end_date: returns_qs = returns_qs.filter(created_at__lte=end_date)
    metrics["returns"] = returns_qs.count()

    # 7. Refunds
    refunds_qs = RefundTransaction.objects.filter(payment_transaction__order__retailer=retailer, status=RefundTransaction.STATUS_COMPLETED)
    if start_date: refunds_qs = refunds_qs.filter(created_at__gte=start_date)
    if end_date: refunds_qs = refunds_qs.filter(created_at__lte=end_date)
    refunds_agg = refunds_qs.aggregate(total_refunds=Sum('amount'))
    metrics["refunds"] = refunds_agg["total_refunds"] or Decimal("0.00")

    # 8. Payment received
    payments_qs = PaymentTransaction.objects.filter(order__retailer=retailer, status=PaymentTransaction.STATUS_CAPTURED)
    if start_date: payments_qs = payments_qs.filter(created_at__gte=start_date)
    if end_date: payments_qs = payments_qs.filter(created_at__lte=end_date)
    payments_agg = payments_qs.aggregate(total_payments=Sum('amount'))
    metrics["payment_received"] = payments_agg["total_payments"] or Decimal("0.00")

    # 9. Pending settlement
    settlements_qs = RetailerSettlement.objects.filter(retailer=retailer, status=RetailerSettlement.STATUS_PENDING)
    if start_date: settlements_qs = settlements_qs.filter(created_at__gte=start_date)
    if end_date: settlements_qs = settlements_qs.filter(created_at__lte=end_date)
    settlements_agg = settlements_qs.aggregate(total_pending=Sum('settlement_amount'))
    metrics["pending_settlement"] = settlements_agg["total_pending"] or Decimal("0.00")

    # 10. Campaign performance
    from apps.campaigns.services import get_campaign_analytics
    
    metrics["campaign_performance"] = get_campaign_analytics(retailer)

    return metrics


def export_report_to_csv(report_data):
    """
    Converts a report dictionary to a CSV format string.
    Suitable for exporting metrics.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(["Metric", "Value"])
    for key, value in report_data.items():
        if isinstance(value, list):
            # For complex nested metrics like top_categories
            writer.writerow([key, ""])
            if value:
                # Write sub-headers based on dict keys
                sub_keys = list(value[0].keys())
                writer.writerow([""] + sub_keys)
                for item in value:
                    writer.writerow([""] + [item.get(k, "") for k in sub_keys])
        elif isinstance(value, dict):
            writer.writerow([key, ""])
            for sub_key, sub_val in value.items():
                writer.writerow(["", sub_key, sub_val])
        else:
            writer.writerow([key, value])
            
    return output.getvalue()


def build_report_pdf_structure(report_data):
    """
    Provides a dictionary structure ready for PDF generation engine (like ReportLab or WeasyPrint).
    """
    return {
        "title": "Analytics Report",
        "generated_at": str(timezone.now()),
        "summary": {k: v for k, v in report_data.items() if not isinstance(v, (list, dict))},
        "details": {k: v for k, v in report_data.items() if isinstance(v, (list, dict))}
    }
