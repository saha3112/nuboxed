from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Product
from apps.inventory.models import StockItem
from apps.orders.models import Order, OrderItem
from apps.payments.models import Invoice, PaymentTransaction


class Command(BaseCommand):
    help = "Replace legacy demo-order products with matching refurbished catalogue products."

    DEMO_ORDER_PRODUCTS = {
        "ORD-10001": [
            ("ABC Store", "Apple iPhone 15"),
            ("ABC Store", "Apple iPad Air 11-inch (M2)"),
        ],
        "ORD-10002": [
            ("XYZ Store", "Dell XPS 13"),
        ],
    }

    @transaction.atomic
    def handle(self, *args, **options):
        updated = 0
        for number, product_specs in self.DEMO_ORDER_PRODUCTS.items():
            order = Order.objects.select_for_update().filter(number=number).first()
            if not order:
                self.stdout.write(self.style.WARNING(f"Skipped {number}: demo order not found"))
                continue

            items = list(order.items.select_for_update().order_by("id"))
            if len(items) != len(product_specs):
                raise CommandError(
                    f"{number} has {len(items)} items; expected {len(product_specs)}. "
                    "No demo order changes were committed."
                )

            subtotal = Decimal("0.00")
            for item, (store_name, model_name) in zip(items, product_specs):
                product = Product.objects.filter(
                    store__name=store_name,
                    model_name=model_name,
                    is_active=True,
                    status=Product.STATUS_APPROVED,
                ).select_related("store", "retailer").first()
                if not product:
                    raise CommandError(f"Relevant active product not found: {store_name} / {model_name}")

                variant = product.variants.filter(is_active=True).order_by("-is_default", "id").first()
                if not variant:
                    raise CommandError(f"No active variant found for {store_name} / {model_name}")
                stock = StockItem.objects.filter(product=product, variant=variant).select_related("warehouse").first()

                sale_price = variant.discount_price or variant.price or product.discount_price or product.price
                original_price = variant.price or product.price or sale_price
                item.product = product
                item.variant = variant
                item.warehouse = stock.warehouse if stock else None
                item.unit_price = original_price
                item.discount_price = sale_price
                item.line_total = sale_price * item.quantity
                item.save(update_fields=[
                    "product", "variant", "warehouse", "unit_price", "discount_price", "line_total", "updated_at"
                ])
                subtotal += item.line_total
                order.retailer = product.retailer
                updated += 1

            order.subtotal_amount = subtotal
            order.discount_amount = max(Decimal("0.00"), subtotal - sum(
                (item.unit_price * item.quantity for item in items), Decimal("0.00")
            ))
            order.total_amount = subtotal + order.tax_amount + order.shipping_amount
            order.currency_code = "EUR"
            order.save(update_fields=[
                "retailer", "subtotal_amount", "discount_amount", "total_amount", "currency_code", "updated_at"
            ])
            PaymentTransaction.objects.filter(order=order).update(amount=order.total_amount)
            Invoice.objects.filter(order=order).update(total_amount=order.total_amount)
            self.stdout.write(self.style.SUCCESS(f"Updated {number} with relevant catalogue products"))

        self.stdout.write(self.style.SUCCESS(f"Demo order items updated: {updated}"))
