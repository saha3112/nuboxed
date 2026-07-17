# CommerceOS Foundation

## 1. Full project architecture

### Core business positioning

CommerceOS is a Europe-focused marketplace platform where multiple retailers operate inside one controlled commerce ecosystem. The platform must support:

- multi-retailer operations
- country-aware VAT and invoicing
- GDPR-aligned customer data handling
- multilingual and multicurrency readiness
- future integrations with local couriers, PSPs, ERP systems, and tax tools

### High-level architecture

- Web frontend
  - customer storefront
  - retailer backoffice
  - operations/admin console
- API gateway layer
  - REST APIs via Django REST Framework
  - versioned endpoints under `/api/v1/`
  - token/session auth strategy prepared for web and future Flutter clients
- Domain services inside Django apps
  - identity and access
  - retailer onboarding
  - catalog and pricing
  - inventory
  - cart and checkout
  - orders and fulfillment
  - payments
  - promotions
  - logistics
  - customer support
  - analytics and reporting
- Async processing
  - Celery workers
  - Redis broker/cache
  - scheduled jobs for settlement, stock sync, notifications, exports
- Data layer
  - MySQL transactional database
  - Redis cache and queue broker
  - S3-compatible object storage for product media, invoices, exports, and retailer documents
- Integration layer
  - payment providers
  - courier APIs
  - email and SMS providers
  - ERP/PIM/OMS connectors
- Observability and platform ops
  - structured logging
  - metrics and health endpoints
  - audit trails
  - exception tracking

### Architectural style

- Modular monolith first
- Clear app/domain boundaries
- Service-layer business logic
- API-first contract design
- Event-driven async jobs for slow or external tasks

This keeps complexity manageable early while preserving a clean migration path to service extraction later if scale requires it.

## 2. Django app structure

### Platform apps

- `apps.common`
  - shared mixins, utilities, base models, constants
- `apps.core`
  - platform settings entities, countries, currencies, languages, VAT configuration
- `apps.users`
  - user accounts, profile basics, authentication helpers
- `apps.accounts`
  - organization, retailer, staff membership, legal entity data
- `apps.rbac`
  - roles, permissions, scoped access rules
- `apps.audit`
  - activity logs, access logs, admin actions
- `apps.notifications`
  - email, SMS, in-app notifications, templates
- `apps.files`
  - upload orchestration, S3 storage metadata

### Commerce apps

- `apps.catalog`
  - categories, attributes, brands, products, variants, media
- `apps.pricing`
  - price lists, VAT-inclusive and VAT-exclusive pricing, regional pricing
- `apps.inventory`
  - warehouses, stock, reservations, stock movements
- `apps.cart`
  - carts, cart items, saved carts
- `apps.checkout`
  - addresses, shipping selections, tax summary, final review
- `apps.orders`
  - orders, order items, status workflows, order notes
- `apps.payments`
  - payment intents, transactions, refunds, settlement references
- `apps.fulfillment`
  - picking, packing, shipment creation, tracking
- `apps.promotions`
  - coupons, campaigns, rules, bundles
- `apps.reviews`
  - product and retailer reviews, moderation
- `apps.support`
  - tickets, disputes, returns, claims

### Marketplace and operations apps

- `apps.marketplace`
  - retailer onboarding, KYC/KYB, commission policies, retailer lifecycle
- `apps.settlements`
  - payouts, commission calculations, statements
- `apps.analytics`
  - dashboards, aggregates, exports
- `apps.integrations`
  - PSP, courier, ERP, webhook, import/export connectors

### API surface apps

- `api.public`
  - storefront APIs
- `api.retailer`
  - seller dashboard APIs
- `api.admin`
  - platform operations APIs
- `api.internal`
  - internal service and webhook endpoints

## 3. Database module plan

### Foundational domain groups

1. Identity and access
   - users
   - retailer memberships
   - roles
   - permission assignments
   - refresh/session token references

2. Organization and retailer
   - retailer profile
   - business identity
   - VAT registration
   - operating countries
   - payout configuration
   - compliance documents

3. Catalog and merchandising
   - categories
   - brands
   - product templates
   - product variants
   - attributes and attribute values
   - product media
   - retailer listings

4. Pricing and tax
   - base prices
   - sale prices
   - tax classes
   - VAT rules
   - country/currency pricing

5. Inventory and fulfillment
   - warehouses
   - stock balances
   - stock reservations
   - stock movement ledger
   - shipment packages
   - tracking events

6. Customer commerce
   - customer profile
   - addresses
   - carts
   - wishlists
   - orders
   - payments
   - refunds

7. Marketplace finance
   - commissions
   - retailer statements
   - payout batches
   - invoice metadata

8. Engagement and support
   - reviews
   - tickets
   - returns
   - disputes
   - notifications

9. Control and observability
   - audits
   - idempotency records
   - webhook deliveries
   - background job references

### Database design principles

- UUID primary keys for public-facing entities
- integer surrogate keys acceptable for internal lookup tables if needed
- soft delete only where business recovery is required
- append-only ledgers for money, stock, and audit events
- explicit `created_at`, `updated_at`, `created_by`, `updated_by` where appropriate
- indexing on retailer, order status, payment status, SKU, slug, email, external reference
- country and currency fields normalized to ISO standards

### MySQL usage plan

- single primary transactional database initially: `nuboxed`
- separate schemas are optional later, but start with one database and strong naming conventions
- read replicas can be added later for analytics-heavy workloads

## 4. Role and permission plan

### Platform roles

- `super_admin`
  - full platform authority
- `ops_admin`
  - order operations, logistics, support, exception handling
- `finance_admin`
  - commissions, settlements, refunds, reports
- `compliance_admin`
  - retailer verification, KYC/KYB review, document approvals
- `support_agent`
  - customer service and dispute handling

### Retailer roles

- `retailer_owner`
  - business owner and full tenant control
- `retailer_admin`
  - full retailer team management except ownership transfer
- `catalog_manager`
  - products, attributes, pricing, promotions
- `inventory_manager`
  - stock, warehouse, fulfillment prep
- `order_manager`
  - orders, returns, customer order communications
- `finance_manager`
  - payout visibility, invoices, settlement reports
- `viewer`
  - read-only operational access

### Customer roles

- `customer`
  - storefront and account operations
- `guest`
  - pre-registration commerce flow with restricted capabilities

### Permission model

- RBAC baseline with optional object-scope rules
- permissions grouped by domain and action
  - `catalog.product.read`
  - `catalog.product.write`
  - `orders.manage`
  - `settlements.view`
- tenant scoping enforced at queryset and service layer
- elevated admin actions require audit logging

## 5. Development phases

### Phase 1: Platform foundation

- Django project bootstrap
- environment and settings split
- MySQL, Redis, Celery, S3 configuration
- custom user model
- retailer/account model
- RBAC base
- audit logging base
- API standards and versioning
- CI/CD and local developer tooling

### Phase 2: Catalog and retailer onboarding

- retailer registration and approval workflow
- categories, brands, products, variants
- media uploads
- retailer listings
- basic price and tax structures

### Phase 3: Inventory, cart, and checkout

- warehouses and stock
- cart APIs
- shipping address flows
- checkout calculation engine
- VAT summary and shipping methods

### Phase 4: Orders, payments, and fulfillment

- order lifecycle
- payment intent and transaction tracking
- refund workflows
- shipment creation and tracking
- order notifications

### Phase 5: Marketplace finance and support

- commissions
- retailer settlement statements
- returns and disputes
- review moderation
- support ticketing

### Phase 6: Optimization and expansion

- analytics and exports
- performance tuning
- country-specific payment/courier integrations
- multilingual and multicurrency expansion
- search and recommendation improvements

## 6. Security plan

### Core security controls

- custom user model from day one
- strong password hashing using Django defaults
- optional 2FA for admin and retailer accounts
- JWT or token-based auth for mobile-readiness, with secure rotation policy
- CSRF protection for session-authenticated web flows
- rate limiting on auth, checkout, and public search endpoints
- field-level validation and serializer-level sanitization
- strict file upload validation and content-type control
- signed S3 upload and access patterns where applicable
- encrypted secrets via environment variables

### Data protection

- GDPR-aware consent and retention policies
- minimize storage of personal data
- separate legal/compliance document access controls
- audit trails for sensitive actions
- PII-aware logging rules

### Marketplace-specific security

- tenant data isolation
- idempotency for payment and checkout actions
- webhook signature verification
- anti-fraud hooks for suspicious orders
- backoffice privilege segregation

## 7. API-first strategy

### API design principles

- frontend consumes the same APIs as future mobile apps
- stable versioned namespace: `/api/v1/`
- consistent response envelope for errors and pagination
- domain-based endpoint grouping
- OpenAPI schema generation from the beginning
- idempotency keys for payment/order creation endpoints
- filter/search/sort conventions shared across modules

### API segmentation

- public storefront API
- authenticated customer API
- retailer management API
- internal/admin API
- webhook and integration API

### API quality standards

- serializers separate transport and domain concerns
- service layer keeps views thin
- explicit error codes
- pagination defaults
- per-endpoint permission classes
- contract tests for critical endpoints

## 8. Future mobile-readiness plan

### Flutter-readiness requirements

- token-based authentication support
- consistent JSON structures
- API versioning discipline
- locale/currency metadata endpoints
- image/media URLs optimized for mobile
- order, cart, checkout, and account flows independent of web-only sessions
- refresh-token rotation or secure mobile session equivalent

### Mobile-ready backend conventions

- avoid HTML-specific assumptions in business logic
- place presentation logic in frontend, not API
- support partial sync patterns for catalog and order history
- use stable enums and documented statuses
- expose minimal but sufficient metadata for app rendering

## Europe-focused concerns

- VAT by country and tax class
- invoice and credit-note generation
- multilingual content readiness
- multicurrency display and settlement strategy
- GDPR compliance
- support for regional shipping and payment methods

## Recommended implementation strategy

Start with a modular monolith in Django. Keep marketplace boundaries explicit in models, services, and permissions. Introduce event-driven async processing for non-transactional work. Only split services later if scaling pressure is proven.
