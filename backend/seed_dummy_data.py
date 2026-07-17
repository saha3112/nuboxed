import os
import django
import random
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.users.models import User
from apps.retailers.models import Retailer
from apps.catalog.models import Category, Product, ProductVariant
from apps.inventory.models import Warehouse, StockItem
from apps.orders.models import Order, OrderItem
from apps.payments.models import PaymentTransaction, Invoice
from apps.returns_app.models import ReturnRequest

print("Starting to seed dummy data...")

# 1. Retailer
from apps.accounts.models import Account

retailer_user = User.objects.get(email='retailer@nuboxed.com')
account, _ = Account.objects.get_or_create(name="Test Retailer Account", defaults={'owner': retailer_user})
retailer, _ = Retailer.objects.get_or_create(
    legal_name="Test Retailer Store",
    defaults={'display_name': 'Test Retailer Store', 'support_email': retailer_user.email, 'status': 'approved', 'account': account}
)

# 2. Categories
cat_electronics, _ = Category.objects.get_or_create(name="Electronics", slug="electronics")
cat_clothing, _ = Category.objects.get_or_create(name="Clothing", slug="clothing")

from apps.stores.models import Store
store, _ = Store.objects.get_or_create(retailer=retailer, name="Test Store")

# 3. Products
prod1, _ = Product.objects.get_or_create(
    name="Wireless Headphones",
    slug="wireless-headphones",
    retailer=retailer,
    store=store,
    category=cat_electronics,
    defaults={'description': "High quality noise cancelling headphones.", 'price': Decimal('199.99'), 'sku': 'PROD-WH-01'}
)

prod2, _ = Product.objects.get_or_create(
    name="Cotton T-Shirt",
    slug="cotton-tshirt",
    retailer=retailer,
    store=store,
    category=cat_clothing,
    defaults={'description': "100% Cotton plain t-shirt.", 'price': Decimal('19.99'), 'sku': 'PROD-TS-02'}
)

# 4. Variants
var1, _ = ProductVariant.objects.get_or_create(
    product=prod1,
    sku="WH-BLK-01",
    defaults={'price': Decimal('199.99')}
)

var2, _ = ProductVariant.objects.get_or_create(
    product=prod2,
    sku="TS-WHT-M",
    defaults={'price': Decimal('19.99')}
)

# 5. Inventory Stock
warehouse, _ = Warehouse.objects.get_or_create(retailer=retailer, code="WH-01", defaults={'name': 'Main Warehouse'})
StockItem.objects.update_or_create(product=prod1, variant=var1, warehouse=warehouse, defaults={'on_hand_quantity': 50})
StockItem.objects.update_or_create(product=prod2, variant=var2, warehouse=warehouse, defaults={'on_hand_quantity': 200})

# 6. Orders
customer, _ = User.objects.get_or_create(username='customer', defaults={'email': 'customer@example.com'})

order1, _ = Order.objects.get_or_create(
    number="ORD-10001",
    defaults={
        'customer': customer,
        'retailer': retailer,
        'total_amount': Decimal('219.98'),
        'status': 'confirmed'
    }
)
OrderItem.objects.get_or_create(order=order1, variant=var1, defaults={'quantity': 1, 'unit_price': Decimal('199.99'), 'product': prod1, 'line_total': Decimal('199.99'), 'warehouse': warehouse})
OrderItem.objects.get_or_create(order=order1, variant=var2, defaults={'quantity': 1, 'unit_price': Decimal('19.99'), 'product': prod2, 'line_total': Decimal('19.99'), 'warehouse': warehouse})

order2, _ = Order.objects.get_or_create(
    number="ORD-10002",
    defaults={
        'customer': customer,
        'retailer': retailer,
        'total_amount': Decimal('19.99'),
        'status': 'delivered'
    }
)
OrderItem.objects.get_or_create(order=order2, variant=var2, defaults={'quantity': 1, 'unit_price': Decimal('19.99'), 'product': prod2, 'line_total': Decimal('19.99'), 'warehouse': warehouse})

# 7. Payments & Invoices
from apps.payments.models import PaymentGateway
gateway, _ = PaymentGateway.objects.get_or_create(code="stripe", defaults={'name': 'Stripe', 'provider': 'stripe', 'status': 'active', 'is_live': False})

PaymentTransaction.objects.get_or_create(
    order=order1,
    transaction_number="TXN-10001",
    defaults={'amount': Decimal('219.98'), 'gateway': gateway, 'status': 'success'}
)
from django.utils import timezone
Invoice.objects.get_or_create(
    order=order1,
    invoice_number="INV-10001",
    defaults={'total_amount': Decimal('219.98'), 'status': 'paid', 'retailer': retailer, 'customer': customer, 'due_date': timezone.now().date() + timezone.timedelta(days=30)}
)

print("Dummy data successfully injected into all major modules!")
