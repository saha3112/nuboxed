# CommerceOS Backend Setup

## Stack

- Django
- Django REST Framework
- MySQL
- Redis
- Celery
- S3-compatible storage
- JWT authentication

## Folder structure

- `config/` Django project configuration
- `config/settings/` environment-specific settings
- `api/v1/` versioned API entrypoints
- `apps/common/` shared base models and utilities
- `apps/*` business domain apps
- `requirements.txt` install entrypoint

## Apps

- `accounts`
- `rbac`
- `retailers`
- `stores`
- `catalog`
- `inventory`
- `orders`
- `payments`
- `shipments`
- `returns_app`
- `marketplace`
- `notifications`
- `reports`
- `cms`
- `settings_app`

## Setup

1. Create a virtual environment and activate it.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy the environment file:

```bash
cp .env.example .env
```

4. Confirm MySQL database access:
   - database: `nuboxed`
   - user: `root`
   - password: `Chandan.1`

5. Run migrations:

```bash
python manage.py makemigrations
python manage.py migrate
```

6. Create an admin user:

```bash
python manage.py createsuperuser
```

7. Start the API server:

```bash
python manage.py runserver
```

## JWT endpoints

- `POST /api/v1/auth/register/`
- `POST /api/v1/auth/login/`
- `POST /api/v1/auth/logout/`
- `GET /api/v1/auth/me/`
- `POST /api/v1/auth/token/`
- `POST /api/v1/auth/token/refresh/`
- `POST /api/v1/auth/password-reset/request/`
- `POST /api/v1/auth/password-reset/confirm/`
- `POST /api/v1/auth/email-verification/request/`
- `POST /api/v1/auth/email-verification/confirm/`

## RBAC

Seed the default roles and permissions with:

```bash
python manage.py seed_rbac
```

Default system roles:

- Super Admin
- Admin Staff
- Retailer Owner
- Retailer Manager
- Product Manager
- Stock Manager
- Order Manager
- Finance Manager
- Report Viewer
- Customer

Access rules:

- Super Admin can access everything.
- Retailer users must be scoped to their own account or store.
- Customers can access only their own data.
- DRF defaults to authenticated permission checks through `apps.rbac.permissions.CommerceAccessPermission`.

## Utility endpoints

- `GET /api/v1/health/`
- `GET /api/v1/schema/`
- `GET /api/v1/docs/`

## Super Admin panel

- URL: `/super-admin/`
- Login: `/super-admin/login/`
- Access: global `Super Admin` only

The panel foundation includes:

- executive dashboard cards
- responsive module tables
- filters and status badges
- create/edit forms
- modal shell for quick actions
- CSV export buttons
- management modules for retailers, stores, users, roles, permissions, categories, products, sliders, featured content, gateways, courier partners, connectors, reports, and settings

## Retailer module

Retailer dashboard routes:

- `/retailer/`
- `/retailer/profile/`
- `/retailer/stores/new/`
- `/retailer/stores/<id>/edit/`
- `/retailer/staff/`

Retailer API routes:

- `POST /api/v1/retailers/register/`
- `GET/PATCH /api/v1/retailers/profile/`
- `GET/POST /api/v1/retailers/stores/`
- `GET/PATCH /api/v1/retailers/stores/<id>/`
- `GET/POST /api/v1/retailers/staff/`
- `POST /api/v1/retailers/<id>/approve/`

Rules enforced in this module:

- retailer users are scoped to their own retailer account and store membership
- empty store logo/banner sections are hidden in retailer-facing templates
- external marketplace connectors are not exposed to retailers and remain Super Admin only

## Catalog module

Catalog API routes:

- `GET /api/v1/catalog/categories/tree/`
- `GET/POST /api/v1/catalog/categories/`
- `GET/PATCH/DELETE /api/v1/catalog/categories/<id>/`
- `POST /api/v1/catalog/categories/<id>/reorder/`
- `GET/POST /api/v1/catalog/brands/`
- `GET/PATCH/DELETE /api/v1/catalog/brands/<id>/`
- `GET/POST /api/v1/catalog/attributes/`
- `GET/POST /api/v1/catalog/attribute-options/`
- `GET/POST /api/v1/catalog/retailer/products/`
- `GET/PATCH /api/v1/catalog/retailer/products/<id>/`
- `GET/POST /api/v1/catalog/retailer/products/<id>/variants/`
- `GET/POST /api/v1/catalog/retailer/products/<id>/media/`
- `GET /api/v1/catalog/admin/products/`
- `POST /api/v1/catalog/admin/products/<id>/approve/`
- `POST /api/v1/catalog/admin/products/<id>/reject/`
- `GET /api/v1/catalog/products/<slug>/`

Catalog UI routes:

- `/retailer/catalog/products/`
- `/retailer/catalog/products/new/`
- `/retailer/catalog/products/<id>/edit/`
- `/retailer/catalog/products/<id>/variants/new/`
- `/retailer/catalog/products/<id>/media/new/`
- `/products/<slug>/`

Catalog rules enforced:

- retailers upload and manage only their own products
- super admin/backoffice can manage all products
- category-wise marketplace inventory is derived from retailer-uploaded products
- product detail page includes image carousel behavior and zoom interaction

## Inventory module

Inventory API routes:

- `GET/POST /api/v1/inventory/warehouses/`
- `GET/POST /api/v1/inventory/delivery-locations/`
- `GET/POST /api/v1/inventory/category-delivery-rules/`
- `GET/POST /api/v1/inventory/product-delivery-rules/`
- `GET /api/v1/inventory/stock-items/`
- `GET /api/v1/inventory/ledger/`
- `POST /api/v1/inventory/adjustments/`
- `GET/POST /api/v1/inventory/offline-sales/`
- `GET /api/v1/inventory/low-stock-alerts/`
- `POST /api/v1/inventory/eta/estimate/`

Inventory UI routes:

- `/retailer/inventory/`
- `/retailer/inventory/warehouses/new/`
- `/retailer/inventory/delivery-locations/new/`
- `/retailer/inventory/category-delivery/new/`
- `/retailer/inventory/product-delivery/new/`
- `/retailer/inventory/adjustments/new/`
- `/retailer/inventory/offline-sales/new/`

Inventory rules enforced:

- every stock movement is recorded in `StockLedger`
- confirmed online orders reduce stock automatically
- cancelled orders restore stock automatically
- returns restore stock only after QC approval
- retailer offline sales reduce stock and are tracked separately
- low stock alerts are raised from item thresholds
- pincode/location ETA supports manual postal code entry, browser geolocation, and saved customer default address fallback
- delivery ETA precedence is product rule -> category rule -> delivery location rule -> warehouse defaults -> store default

## Marketplace frontend

Main storefront routes:

- `/`
- `/stores/`
- `/stores/<slug>/`
- `/category/<slug>/`
- `/products/`
- `/seller-comparison/`
- `/products/<slug>/`
- `/cart/`
- `/checkout/`
- `/dashboard/`
- `/contact/`

Frontend features included:

- sticky ecommerce header with dropdown menus
- dynamic store dropdown links
- dynamic device/category dropdown
- homepage slider, featured banners, featured categories, featured products, category-wise products
- store directory and retailer store pages
- category and product listing pages
- seller comparison page
- shared marketplace styling across public pages
- product detail page with carousel behavior and zoom
- session-based cart and wishlist counters
- persistent delivery location chooser in the storefront header
- ETA rendering on product detail, seller comparison, and checkout
- persistent database-backed cart with session sync

## Website cart and order flow

Storefront order features:

- persistent cart and cart items backed by MySQL models
- address selection from saved customer addresses
- new address capture during checkout
- pincode-aware shipping and delivery estimate during checkout
- coupon-ready order structure with discount fields
- tax and shipping calculation at cart and order level
- payment method selection
- order creation split by retailer when the cart contains multiple sellers
- order timeline history for status progression
- internal courier shipment creation for website orders

Operational rules enforced:

- stock is reserved during checkout when the order is created in `pending`
- reserved stock is deducted only after order confirmation
- website orders follow the internal courier flow through shipment creation

## Fulfillment engine

Fulfillment routing rules:

- `website` order -> `internal_courier`
- `amazon` order -> `amazon_fulfillment`
- `flipkart` order -> `flipkart_fulfillment`
- `ebay` order -> `ebay_fulfillment`
- `shopify` or `woocommerce` order -> `platform_fulfillment`
- offline sale -> `offline_flow`

System behavior:

- courier booking is created only for website orders from our own marketplace
- external marketplace orders never create internal courier booking in CommerceOS
- external marketplace fulfillment remains sync-only for order, stock, return, refund, settlement, and reporting
- offline sales register offline fulfillment records only

## Courier integration

Super Admin manages:

- courier partners
- API credentials
- country-wise serviceability
- postal-code serviceability rules
- courier rules
- bookings, pickups, return pickups, and performance reports

Courier API routes:

- `GET/POST /api/v1/shipments/courier-partners/`
- `GET/POST /api/v1/shipments/credentials/`
- `GET/POST /api/v1/shipments/country-serviceability/`
- `GET/POST /api/v1/shipments/serviceability-rules/`
- `GET/POST /api/v1/shipments/courier-rules/`
- `GET /api/v1/shipments/fulfillments/`
- `GET /api/v1/shipments/shipments/`
- `POST /api/v1/shipments/shipments/create/`
- `GET /api/v1/shipments/shipments/<id>/`
- `POST /api/v1/shipments/shipments/<id>/label/`
- `GET /api/v1/shipments/shipments/<id>/tracking/`
- `POST /api/v1/shipments/shipments/pickups/`
- `POST /api/v1/shipments/shipments/returns/`
- `POST /api/v1/shipments/serviceability/check/`
- `POST /api/v1/shipments/webhook/delivery/`
- `GET /api/v1/shipments/reports/performance/`

Rules enforced:

- courier booking is created only for website orders
- external marketplace orders never create courier bookings in CommerceOS
- courier label, pickup, reverse logistics, and tracking flows only apply to internal website shipments
- webhook handling updates shipment tracking and order timeline entries

## Celery

Run a worker with:

```bash
celery -A config worker -l info
```

## Settings modules

- local: `config.settings.local`
- staging: `config.settings.staging`
- production: `config.settings.production`

Set `DJANGO_SETTINGS_MODULE` in the environment to switch between them.
