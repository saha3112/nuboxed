from typing import Dict, Any
import hashlib
import json
import logging
import re
import time
import requests
from types import SimpleNamespace
from django.db.models import Q, Sum
from apps.common.encryption import decrypt, encrypt
from apps.marketplace.models import MarketplaceListing, MarketplaceStoreMapping, MarketplaceSyncJob
from apps.catalog.models import Product, ProductVariant
from apps.inventory.models import StockItem
from apps.inventory.services import ensure_default_warehouse, sync_product_stock
from django.utils import timezone
from datetime import timedelta
from apps.marketplace.drivers.base import BaseMarketplaceDriver

logger = logging.getLogger(__name__)


class MockBaseDriver(BaseMarketplaceDriver):
    """
    Staging driver that simulates integration calls for validation and testing.
    """

    def refresh_token(self) -> Dict[str, Any]:
        self.connection.access_token = f"mock_access_token_{self.connection.connector.code}_{timezone.now().timestamp()}"
        self.connection.token_expires_at = timezone.now() + timedelta(hours=2)
        self.connection.save()
        return {"status": "refreshed", "expires_at": self.connection.token_expires_at}

    def sync_products(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        return {
            "status": "success",
            "synced_count": len(payload.get("items", [])) if payload else 1,
            "provider": self.__class__.__name__
        }

    def sync_prices(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        return {
            "status": "success",
            "updated_prices": len(payload.get("prices", [])) if payload else 1,
            "provider": self.__class__.__name__
        }

    def sync_stock(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        return {
            "status": "success",
            "updated_stock": len(payload.get("stock", [])) if payload else 1,
            "provider": self.__class__.__name__
        }

    def import_orders(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        return {
            "status": "success",
            "imported_orders": [
                {
                    "external_order_id": f"EXT-{self.connection.connector.code.upper()}-12345",
                    "status": "unfulfilled",
                    "amount": 250.00,
                    "currency": "EUR"
                }
            ],
            "provider": self.__class__.__name__
        }

    def sync_returns(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        return {
            "status": "success",
            "synced_returns": 1,
            "provider": self.__class__.__name__
        }

    def sync_refunds(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        return {
            "status": "success",
            "synced_refunds": 1,
            "provider": self.__class__.__name__
        }

    def sync_settlements(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        return {
            "status": "success",
            "payout_amount": 1250.00,
            "currency": "EUR",
            "provider": self.__class__.__name__
        }

    def handle_webhook(self, headers: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "processed",
            "event": payload.get("event_type", "unknown"),
            "provider": self.__class__.__name__
        }


class AmazonDriver(MockBaseDriver):
    """Amazon SP-API driver.

    LWA is used for the connection check and request authentication. AWS IAM
    keys are optional and retained only for older/private signing setups.
    """
    TOKEN_URL = "https://api.amazon.com/auth/o2/token"

    def _credentials(self, environment=None):
        stored = self.connection.credentials or {}
        profile = stored.get(environment) if environment else None
        if isinstance(profile, dict):
            values = dict(profile)
        elif environment and any(isinstance(stored.get(name), dict) for name in ("sandbox", "production")):
            values = {}
        else:
            values = dict(stored)
        # The admin form calls this field Client Identifier, while Amazon's
        # LWA token endpoint calls it client_id. Accept both names so older
        # saved connections and API-created connections behave identically.
        values["client_id"] = values.get("client_id") or values.get("client_identifier")
        selected_environment = environment or values.get("environment", "sandbox")
        token_key = "live_refresh_token" if selected_environment == "production" else "sandbox_refresh_token"
        values["refresh_token"] = values.get(token_key) or values.get("refresh_token") or values.get("sandbox_refresh_token")
        for key in ("client_secret", "refresh_token", "aws_secret_access_key"):
            if values.get(key):
                values[key] = decrypt(values[key])
        return values

    def refresh_token(self, environment=None) -> Dict[str, Any]:
        c = self._credentials(environment)
        required = ("client_id", "client_secret", "refresh_token")
        missing = [key for key in required if not c.get(key)]
        if missing:
            raise ValueError("Missing Amazon credentials: " + ", ".join(missing))
        response = requests.post(self.TOKEN_URL, data={
            "grant_type": "refresh_token",
            "refresh_token": c["refresh_token"],
            "client_id": c["client_id"],
            "client_secret": c["client_secret"],
        }, timeout=20)
        if response.status_code >= 400:
            raise ValueError(f"Amazon LWA token error ({response.status_code}): {response.text[:500]}")
        data = response.json()
        self.connection.access_token = data.get("access_token", "")
        rotated_refresh_token = data.get("refresh_token", c["refresh_token"])
        encrypted_refresh_token = encrypt(rotated_refresh_token)
        self.connection.refresh_token = encrypted_refresh_token
        stored_credentials = dict(self.connection.credentials or {})
        if environment in ("sandbox", "production"):
            profile = dict(stored_credentials.get(environment) or {})
            token_key = "live_refresh_token" if environment == "production" else "sandbox_refresh_token"
            profile[token_key] = encrypted_refresh_token
            profile["refresh_token"] = encrypted_refresh_token
            profile["token_refreshed_at"] = timezone.now().isoformat()
            fingerprint = hashlib.sha256(rotated_refresh_token.encode("utf-8")).hexdigest()[-12:]
            previous_fingerprint = profile.get("refresh_token_fingerprint")
            profile["refresh_token_fingerprint"] = fingerprint
            profile["refresh_token_continuity"] = "rotated" if previous_fingerprint and previous_fingerprint != fingerprint else "unchanged"
            profile["last_refresh_result"] = "success"
            profile["last_refresh_error"] = ""
            stored_credentials[environment] = profile
            # Keep legacy consumers and the currently selected mode in sync.
            if stored_credentials.get("environment") == environment:
                stored_credentials[token_key] = encrypted_refresh_token
                stored_credentials["refresh_token"] = encrypted_refresh_token
        else:
            stored_credentials["refresh_token"] = encrypted_refresh_token
        stored_credentials["token_refreshed_at"] = timezone.now().isoformat()
        self.connection.credentials = stored_credentials
        self.connection.token_expires_at = timezone.now() + timedelta(seconds=int(data.get("expires_in", 3600)) - 60)
        self.connection.status = self.connection.STATUS_ACTIVE
        self.connection.error_message = ""
        self.connection.save(update_fields=["access_token", "refresh_token", "credentials", "token_expires_at", "status", "error_message", "updated_at"])
        return {"status": "connected", "expires_at": self.connection.token_expires_at, "token_type": data.get("token_type", "bearer")}

    def _api_request(self, method, path, params=None, body=None):
        c = self._credentials()
        # Refresh five minutes before expiry so an in-flight Amazon request
        # never starts with an access token that is about to expire.
        refresh_deadline = timezone.now() + timedelta(minutes=5)
        if not self.connection.access_token or not self.connection.token_expires_at or self.connection.token_expires_at <= refresh_deadline:
            self.refresh_token()
        endpoint = (c.get("endpoint") or "https://sandbox.sellingpartnerapi-eu.amazon.com").rstrip("/")
        url = endpoint + path
        headers = {"accept": "application/json", "x-amz-access-token": self.connection.access_token, "content-type": "application/json", "user-agent": "Nuboxed/1.0"}
        # SP-API uses the LWA access token directly. AWS IAM/SigV4 is no
        # longer required for SP-API requests, so never add a stale signature.
        # Do not send a JSON body on GET requests. Amazon's API Gateway can
        # reject an otherwise valid Listings/Orders request as an HTML 400
        # when it receives the synthetic `{}` body that requests sends here.
        request_kwargs = {"params": params, "headers": headers, "timeout": 15}
        if method.upper() not in {"GET", "HEAD"}:
            request_kwargs["data"] = json.dumps(body or {}, separators=(",", ":"))
        response = None
        last_network_error = None
        for attempt in range(2):
            try:
                response = requests.request(method, url, **request_kwargs)
                break
            except requests.exceptions.RequestException as exc:
                last_network_error = exc
                if attempt == 0:
                    time.sleep(0.4)
        if response is None:
            raise ConnectionError(
                f"Amazon endpoint is temporarily unreachable ({endpoint}). "
                f"Check DNS/internet access and retry shortly: {last_network_error}"
            )
        if response.status_code >= 400:
            request_id = response.headers.get("x-amzn-requestid") or response.headers.get("x-amzn-request-id")
            suffix = f" [request_id={request_id}]" if request_id else ""
            raise ValueError(f"Amazon SP-API error ({response.status_code}){suffix}: {response.text[:700]}")
        return response.json() if response.content else {}

    def _marketplace_id(self):
        value = self._credentials().get("marketplace_id")
        if not value:
            raise ValueError("Marketplace ID is required for Amazon product and inventory sync.")
        return value

    def _items(self, payload):
        if payload and payload.get("items"):
            resolved = []
            for item in payload["items"]:
                if not isinstance(item, dict):
                    continue
                listing = item.get("listing")
                if listing:
                    resolved.append({"listing": listing})
                    continue
                sku = (item.get("sku") or "").strip()
                if not sku:
                    continue
                exact = MarketplaceListing.objects.filter(
                    connection=self.connection, seller_sku=sku, is_active=True,
                ).select_related("product", "variant", "fulfillment_location")
                if exact.exists():
                    resolved.extend({"listing": listing} for listing in exact)
                    continue
                # Local stock changes carry the Nuboxed variant/product SKU.
                # A variant may have multiple Amazon offer SKUs, so return all
                # of its active mappings for reconciliation.
                mapped = MarketplaceListing.objects.filter(
                    connection=self.connection, is_active=True,
                ).filter(
                    Q(variant__sku=sku) | Q(product__sku=sku)
                ).select_related("product", "variant", "fulfillment_location")
                resolved.extend({"listing": listing} for listing in mapped)
            return resolved
        qs = MarketplaceListing.objects.filter(connection=self.connection, is_active=True).select_related("product", "variant", "fulfillment_location")
        return [{"listing": listing} for listing in qs]

    def _listing_body(self, listing):
        product = listing.product
        sku = listing.seller_sku
        stock_qs = StockItem.objects.filter(product=product, variant=listing.variant, warehouse__retailer=product.retailer)
        if listing.fulfillment_location_id:
            stock_qs = stock_qs.filter(warehouse_id=listing.fulfillment_location_id)
        quantity = stock_qs.aggregate(total=Sum("on_hand_quantity"), reserved=Sum("reserved_quantity"))
        available = max(0, int(quantity["total"] or 0) - int(quantity["reserved"] or 0))
        return sku, available, {
            # Offer-only updates work for an SKU already present in Amazon's
            # catalog and avoid inventing an invalid product type. Creating a
            # brand-new ASIN requires Product Type Definitions data first.
            "productType": self._credentials().get("amazon_product_type", "PRODUCT"),
            "requirements": "LISTING_OFFER_ONLY",
            "attributes": {
                "fulfillment_availability": [{"fulfillment_channel_code": "DEFAULT", "quantity": available}],
                "condition_type": [{"value": "new_new", "marketplace_id": listing.marketplace_id or self._marketplace_id()}],
                "purchasable_offer": [{"currency": "EUR", "our_price": [{"schedule": [{"value_with_tax": str(product.discount_price or product.price)}]}], "marketplace_id": listing.marketplace_id or self._marketplace_id()}],
            },
        }

    @staticmethod
    def _listing_asin(data):
        data = data or {}
        identifiers = data.get("identifiers") or []
        if isinstance(identifiers, dict):
            if identifiers.get("asin"):
                return identifiers["asin"]
            identifiers = identifiers.get("identifiers") or identifiers.get("marketplaceIdentifiers") or []
        for identifier in identifiers:
            if isinstance(identifier, dict) and identifier.get("asin"):
                return identifier["asin"]
            if isinstance(identifier, dict):
                nested = identifier.get("identifiers") or identifier.get("marketplaceIdentifiers") or []
                for value in nested if isinstance(nested, list) else [nested]:
                    if isinstance(value, dict) and value.get("asin"):
                        return value["asin"]
        for summary in data.get("summaries") or []:
            if isinstance(summary, dict) and summary.get("asin"):
                return summary["asin"]
        return ""

    @staticmethod
    def _valid_asin(value):
        return bool(re.fullmatch(r"B[0-9A-Z]{9}", (value or "").strip().upper()))

    @staticmethod
    def _listing_product_type(data):
        for summary in (data or {}).get("summaries") or []:
            if isinstance(summary, dict) and summary.get("productType"):
                return summary["productType"]
        for product_type in (data or {}).get("productTypes") or []:
            if isinstance(product_type, dict):
                value = product_type.get("productType") or product_type.get("product_type")
                if value:
                    return value
        return ""

    def _catalog_match(self, listing, marketplace_id):
        """Resolve an ASIN from a local EAN/UPC when the seller SKU is new."""
        identifier = getattr(listing.variant, "barcode", "") if listing.variant else ""
        identifier = identifier or getattr(listing.product, "barcode", "")
        if not identifier:
            return {}
        for identifier_type in ("EAN", "UPC"):
            try:
                data = self._api_request("GET", "/catalog/2022-04-01/items", params={"marketplaceIds": marketplace_id, "identifiers": identifier, "identifiersType": identifier_type, "includedData": "summaries,identifiers,productTypes"})
            except Exception:
                continue
            items = data.get("items") or []
            if len(items) == 1:
                return items[0]
        return {}

    def sync_products(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        c = self._credentials()
        seller_id = c.get("seller_id")
        if not seller_id:
            raise ValueError("Seller ID is required for Amazon Listings API sync.")
        pushed = []
        for item in self._items(payload):
            listing = item.get("listing") if isinstance(item, dict) else None
            if not listing:
                listing = MarketplaceListing.objects.filter(connection=self.connection, seller_sku=item.get("sku")).first()
            if not listing:
                continue
            sku, quantity, body = self._listing_body(listing)
            marketplace_id = listing.marketplace_id or self._marketplace_id()
            # Offer-only submissions need an existing Amazon catalog match.
            # Resolve it by SKU first; otherwise Amazon returns the opaque 400
            # InvalidInput response seen in the admin panel.
            remote = {}
            asin = listing.external_listing_id if self._valid_asin(listing.external_listing_id) else ""
            if not asin:
                # A product-level Amazon mapping is also valid for an offer
                # when its variant mapping has not yet been copied locally.
                # This lets a new Nubox Seller SKU be submitted instead of
                # being stopped at the preliminary SKU lookup.
                mapped_asins = str(getattr(listing.product, "amazon_asin", "") or "")
                for value in mapped_asins.split(","):
                    value = value.strip().upper()
                    if self._valid_asin(value):
                        asin = value
                        break
            if not asin:
                try:
                    remote = self._api_request("GET", f"/listings/2021-08-01/items/{seller_id}/{sku}", params={"marketplaceIds": marketplace_id, "includedData": "summaries,identifiers,issues,fulfillmentAvailability,offers,productTypes", "issueLocale": "fr_FR" if marketplace_id == "A13V1IB3VIYZZH" else "en_US"})
                except Exception as exc:
                    remote = self._catalog_match(listing, marketplace_id)
                    if not remote:
                        listing.status = "pending"
                        listing.last_error = "Amazon Seller SKU is new in this marketplace. Add a valid Amazon ASIN or EAN/UPC so Nuboxed can submit the offer."
                        listing.save(update_fields=["status", "last_error", "updated_at"])
                        logger.info("Amazon SKU %s is not yet listed: %s", sku, exc)
                        continue
            asin = asin or self._listing_asin(remote)
            if asin:
                body["attributes"]["merchant_suggested_asin"] = [{"value": asin, "marketplace_id": marketplace_id}]
            product_type = self._listing_product_type(remote)
            if product_type:
                body["productType"] = product_type
            # PUT only accepts `issues` in includedData unless validation
            # preview mode is requested. The previous identifiers and
            # fulfillmentAvailability values caused Amazon's opaque 400.
            result = self._api_request("PUT", f"/listings/2021-08-01/items/{seller_id}/{sku}", params={"marketplaceIds": marketplace_id, "includedData": "issues", "issueLocale": "fr_FR" if marketplace_id == "A13V1IB3VIYZZH" else "en_US"}, body=body)
            # Read the authoritative Amazon listing after submission so the
            # admin panel can show ASIN/SKU status and current fulfillment data.
            try:
                remote = self._api_request("GET", f"/listings/2021-08-01/items/{seller_id}/{sku}", params={"marketplaceIds": marketplace_id, "includedData": "summaries,identifiers,issues,fulfillmentAvailability,offers,productTypes", "issueLocale": "fr_FR" if marketplace_id == "A13V1IB3VIYZZH" else "en_US"})
            except Exception as exc:
                # A newly accepted listing can be temporarily unavailable
                # while Amazon processes it. Keep the accepted submission and
                # let the next sync fetch the authoritative listing.
                logger.info("Amazon listing %s is still processing: %s", sku, exc)
                remote = {}
            identifiers = remote.get("identifiers") or result.get("identifiers") or []
            asin = self._listing_asin({"identifiers": identifiers})
            # Store only the catalog ASIN here; a submissionId is temporary
            # and must not be mistaken for an Amazon listing identifier.
            listing.external_listing_id = asin or (listing.external_listing_id if self._valid_asin(listing.external_listing_id) else "")
            listing.last_pushed_quantity = quantity
            listing.last_pushed_at = timezone.now()
            listing.status = "active" if result.get("status") in ("ACCEPTED", "VALID", None) else "pending"
            listing.last_error = "; ".join(issue.get("message", "") for issue in (result.get("issues") or []) if isinstance(issue, dict))
            listing.save(update_fields=["external_listing_id", "last_pushed_quantity", "last_pushed_at", "status", "last_error", "updated_at"])
            pushed.append({"sku": sku, "quantity": quantity})
        return {"status": "success", "synced_count": len(pushed), "items": pushed, "provider": "AmazonDriver"}

    def import_products(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        """Import the seller's Amazon listings and reconcile known SKUs."""
        c = self._credentials()
        seller_id = c.get("seller_id")
        marketplace_id = self._marketplace_id()
        if not seller_id:
            raise ValueError("Seller ID is required to import Amazon listings.")
        imported = matched = unmatched = 0
        imported_items = []
        seen_skus = set()
        fba_quantities = {}
        try:
            inventory = self._api_request("GET", "/fba/inventory/v1/summaries", params={"granularityType": "Marketplace", "granularityId": marketplace_id, "marketplaceIds": marketplace_id})
            for summary in (inventory.get("payload", {}).get("inventorySummaries", []) or []):
                if summary.get("sellerSku"):
                    fba_quantities[summary["sellerSku"]] = int(summary.get("totalQuantity", 0) or 0)
        except Exception as exc:
            logger.info("Amazon FBA quantity pull unavailable; using listing availability: %s", exc)
        page_token = None
        for _ in range(50):
            params = {"marketplaceIds": marketplace_id, "includedData": "summaries,identifiers,issues,offers,fulfillmentAvailability,productTypes", "issueLocale": "fr_FR" if marketplace_id == "A13V1IB3VIYZZH" else "en_US", "pageSize": 20, "sortBy": "lastUpdatedDate", "sortOrder": "DESC"}
            if page_token:
                params["pageToken"] = page_token
            data = self._api_request("GET", f"/listings/2021-08-01/items/{seller_id}", params=params)
            items = data.get("items") or data.get("payload", {}).get("items", [])
            for item in items:
                sku = item.get("sku", "")
                if not sku:
                    continue
                seen_skus.add(sku)
                imported += 1
                asin = self._listing_asin(item)
                summary = next((value for value in (item.get("summaries") or []) if isinstance(value, dict)), {})
                product_type = self._listing_product_type(item)
                availability = item.get("fulfillmentAvailability") or []
                quantity = availability[0].get("quantity") if availability and isinstance(availability[0], dict) else None
                if sku in fba_quantities:
                    quantity = fba_quantities[sku]
                # Keep the catalog and stock reconciliation numeric. Amazon
                # can omit quantity for an offer while it is not sellable;
                # treat that state as zero instead of exposing a misleading
                # dash or leaving stale local stock behind.
                quantity = max(int(quantity or 0), 0)
                listing = MarketplaceListing.objects.filter(connection=self.connection, seller_sku=sku).first()
                # If Amazon and Nuboxed use different Seller SKUs, first try a
                # conservative product/variant title match. This supports
                # translated Amazon titles such as "128 Go - Rose" against a
                # local "128 GB / Red" variant. Never match on product title
                # alone when a product has multiple variants.
                if not listing:
                    remote_name = " ".join((summary.get("itemName") or "").lower().split())
                    candidates = self._variant_title_candidates(remote_name, marketplace_id)
                    if not candidates:
                        candidates = self._auto_create_variant_candidate(remote_name, sku, marketplace_id)
                    if len(candidates) == 1:
                        candidate = candidates[0]
                        listing = MarketplaceListing.objects.create(
                            connection=self.connection,
                            product=candidate.product,
                            variant=candidate.variant,
                            seller_sku=sku,
                            external_listing_id=asin or "",
                            marketplace_id=marketplace_id,
                            fulfillment_location=candidate.fulfillment_location,
                            last_pulled_quantity=quantity,
                            status="active",
                        )
                if listing:
                    matched += 1
                    listing.external_listing_id = asin or listing.external_listing_id
                    listing.last_pulled_quantity = quantity
                    listing.status = "active"
                    listing.last_error = "; ".join(issue.get("message", "") for issue in (item.get("issues") or []) if isinstance(issue, dict))
                    listing.save(update_fields=["external_listing_id", "last_pulled_quantity", "status", "last_error", "updated_at"])
                else:
                    unmatched += 1
                imported_items.append({"sku": sku, "asin": asin, "quantity": quantity, "marketplace_id": marketplace_id, "item_name": summary.get("itemName", ""), "product_type": product_type, "matched": bool(listing)})
            page_token = (data.get("pagination") or {}).get("nextToken") or data.get("nextToken")
            if not page_token or not items:
                break
        # Do not leave an old local mapping marked active after Amazon has
        # confirmed that its seller SKU is absent from the selected country.
        MarketplaceListing.objects.filter(connection=self.connection, marketplace_id=marketplace_id).exclude(seller_sku__in=seen_skus).update(status="pending", last_error="Seller SKU is not listed in the selected Amazon marketplace.", updated_at=timezone.now())
        return {"status": "success", "imported_count": imported, "matched_count": matched, "unmatched_count": unmatched, "items": imported_items[:200], "provider": "AmazonDriver"}

    def _auto_create_variant_candidate(self, remote_name, seller_sku, marketplace_id):
        """Create a missing local variant only for an unambiguous Amazon offer.

        Amazon often has child offers that were never created in Nuboxed. We
        only create a variant when exactly one existing Nubox product name is
        present in the Amazon title and both storage and colour are explicit.
        This prevents an iPhone ASIN from being assigned to another product or
        to a nearby but incorrect colour/storage variant.
        """
        if not remote_name:
            return []

        def words(value):
            return set(re.findall(r"[a-z0-9]+", (value or "").lower()))

        aliases = {
            "red": {"red", "rouge"}, "yellow": {"yellow", "jaune"},
            "blue": {"blue", "bleu"}, "black": {"black", "noir"},
            "green": {"green", "vert"}, "pink": {"pink", "rose"},
            "purple": {"purple", "violet", "mauve"},
            "white": {"white", "blanc", "starlight", "lumiere"},
        }
        remote_words = words(remote_name)
        storage = next(iter(re.findall(r"\b(\d+)\s*(?:gb|go)\b", remote_name)), "")
        colors = [key for key, values in aliases.items() if remote_words.intersection(values)]
        products = [product for product in Product.objects.filter(is_active=True, retailer__isnull=False).select_related("store") if len((product.name or "").strip()) >= 4 and (product.name or "").lower() in remote_name]
        if len(products) != 1 or not storage or len(colors) != 1:
            return []
        product = products[0]
        color = colors[0].title()
        variant_name = f"{storage}GB / {color}"
        existing = [variant for variant in product.variants.all() if storage in (variant.name or "") and color.lower() in (variant.name or "").lower()]
        variant = existing[0] if existing else None
        if variant is None:
            base_sku = re.sub(r"[^A-Z0-9]+", "-", f"AMZ-{seller_sku}".upper()).strip("-")[:92]
            candidate_sku = base_sku or f"AMZ-{product.pk}"
            suffix = 2
            while ProductVariant.objects.filter(sku=candidate_sku).exists():
                candidate_sku = f"{base_sku[:88]}-{suffix}"
                suffix += 1
            variant = ProductVariant.objects.create(
                product=product,
                name=variant_name,
                sku=candidate_sku,
                price=product.price,
                discount_price=product.discount_price,
                is_default=False,
            )
        mapping = MarketplaceStoreMapping.objects.filter(connection=self.connection, store=product.store, is_enabled=True).select_related("warehouse").first()
        warehouse = mapping.warehouse if mapping and mapping.warehouse else ensure_default_warehouse(retailer=product.retailer, store=product.store)
        return [SimpleNamespace(product=product, variant=variant, fulfillment_location=warehouse)]

    def _variant_title_candidates(self, remote_name, marketplace_id):
        """Return one safe local variant candidate for an Amazon title."""
        if not remote_name:
            return []

        def words(value):
            return set(re.findall(r"[a-z0-9]+", (value or "").lower()))

        aliases = {
            "red": {"red", "rouge"}, "yellow": {"yellow", "jaune"},
            "blue": {"blue", "bleu"}, "black": {"black", "noir"},
            "green": {"green", "vert"}, "pink": {"pink", "rose"},
            "purple": {"purple", "violet", "mauve"},
            "white": {"white", "blanc", "starlight", "lumiere", "lumiere"},
        }

        def color_tokens(value):
            token_set = words(value)
            return {key for key, values in aliases.items() if token_set.intersection(values)}

        def storage_tokens(value):
            return set(re.findall(r"\b(\d+)\s*(?:gb|go)\b", (value or "").lower()))

        remote_words = words(remote_name)
        remote_storage = storage_tokens(remote_name)
        remote_colors = color_tokens(remote_name)
        candidates = []
        # Match against every local variant, not only variants that already
        # have a MarketplaceListing. Otherwise the first Amazon import can
        # never create the mapping needed for future SKU/stock sync.
        variants = ProductVariant.objects.filter(
            product__retailer__isnull=False,
            product__is_active=True,
            deleted_at__isnull=True,
        ).select_related("product", "product__store")
        for variant in variants:
            product = variant.product
            product_name = " ".join((product.name or "").lower().split())
            if len(product_name) < 4 or product_name not in remote_name:
                continue
            variant_name = variant.name or ""
            candidate_storage = storage_tokens(variant_name)
            candidate_colors = color_tokens(variant_name)
            score = 0
            if remote_storage and candidate_storage.intersection(remote_storage):
                score += 3
            elif remote_storage and candidate_storage:
                continue
            if remote_colors and candidate_colors.intersection(remote_colors):
                score += 3
            elif remote_colors and candidate_colors:
                continue
            # A variant must match at least one distinguishing attribute.
            if score:
                mapping = MarketplaceStoreMapping.objects.filter(
                    connection=self.connection,
                    store=product.store,
                    is_enabled=True,
                ).select_related("warehouse").first()
                warehouse = mapping.warehouse if mapping and mapping.warehouse else None
                if warehouse is None:
                    warehouse = ensure_default_warehouse(retailer=product.retailer, store=product.store)
                candidates.append((score, SimpleNamespace(
                    product=product,
                    variant=variant,
                    fulfillment_location=warehouse,
                )))
        if not candidates:
            return []
        best_score = max(score for score, _candidate in candidates)
        best = [candidate for score, candidate in candidates if score == best_score]
        # Multiple existing offers for the same variant are valid; collapse
        # only identical local variant candidates before deciding ambiguity.
        unique = {}
        for candidate in best:
            unique[str(candidate.variant.id)] = candidate
        return list(unique.values())

    def sync_stock(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        if payload and payload.get("_direction") == "inbound":
            # Listings availability covers merchant-fulfilled offers as well
            # as FBA. The FBA summaries endpoint alone misses MFN stock and
            # made automatic France stock pull appear to do nothing.
            imported = None
            if payload.get("from_product_import"):
                latest = MarketplaceSyncJob.objects.filter(
                    connection=self.connection,
                    job_type=MarketplaceSyncJob.TYPE_PRODUCT_SYNC,
                    direction=MarketplaceSyncJob.DIRECTION_INBOUND,
                    status=MarketplaceSyncJob.STATUS_COMPLETED,
                ).order_by("-created_at").first()
                if latest:
                    imported = latest.result or {}
            imported = imported or self.import_products(payload)
            updated = []
            stock_groups = {}
            for item in imported.get("items", []):
                sku = item.get("sku")
                listing = MarketplaceListing.objects.filter(connection=self.connection, seller_sku=sku).select_related("product", "variant", "fulfillment_location").first()
                if not listing:
                    continue
                quantity = int(item.get("quantity", 0) or 0)
                group_key = (listing.product_id, listing.variant_id, listing.fulfillment_location_id)
                stock_groups.setdefault(group_key, {"product": listing.product, "variant": listing.variant, "warehouse": listing.fulfillment_location, "quantities": []})["quantities"].append(quantity)
                listing.last_pulled_quantity = quantity
                listing.last_error = ""
                listing.save(update_fields=["last_pulled_quantity", "last_error", "updated_at"])
                updated.append({"sku": sku, "quantity": quantity})
            # Multiple Amazon offers can represent the same Nubox variant.
            # Use the lowest offer quantity locally to avoid overselling, while
            # outbound sync publishes the same local quantity to every offer.
            for group in stock_groups.values():
                sync_product_stock(
                    product=group["product"],
                    variant=group["variant"],
                    warehouse=group["warehouse"],
                    available_quantity=min(group["quantities"] or [0]),
                )
            return {"status": "success", "updated_stock": len(updated), "imported_listings": imported.get("imported_count", 0), "items": updated, "provider": "AmazonDriver"}
        c = self._credentials()
        seller_id = c.get("seller_id")
        if not seller_id:
            raise ValueError("Seller ID is required for Amazon inventory sync.")
        pushed = []
        for item in self._items(payload):
            listing = item.get("listing") if isinstance(item, dict) else None
            if not listing:
                continue
            _sku, quantity, _body = self._listing_body(listing)
            marketplace_id = listing.marketplace_id or self._marketplace_id()
            patch_body = {"productType": "PRODUCT", "patches": [{"op": "merge", "path": "/attributes/fulfillment_availability", "value": [{"fulfillment_channel_code": "DEFAULT", "quantity": quantity}]}]}
            self._api_request("PATCH", f"/listings/2021-08-01/items/{seller_id}/{listing.seller_sku}", params={"marketplaceIds": marketplace_id}, body=patch_body)
            listing.last_pushed_quantity = quantity
            listing.last_pushed_at = timezone.now()
            listing.status = "active"
            listing.last_error = ""
            listing.save(update_fields=["last_pushed_quantity", "last_pushed_at", "status", "last_error", "updated_at"])
            pushed.append({"sku": listing.seller_sku, "quantity": quantity})
        return {"status": "success", "updated_stock": len(pushed), "items": pushed, "provider": "AmazonDriver"}

    def import_orders(self, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        params = {"MarketplaceIds": self._marketplace_id(), "CreatedAfter": (timezone.now() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")}
        try:
            data = self._api_request("GET", "/orders/v0/orders", params=params)
        except ConnectionError as exc:
            return {
                "status": "deferred",
                "imported_orders": [],
                "imported_count": 0,
                "warning": str(exc),
                "provider": "AmazonDriver",
            }
        orders = data.get("payload", {}).get("Orders", [])
        # Order headers do not reliably contain SellerSKU. Pull line items so
        # the tracking service can attribute the sale to a Nuboxed store.
        for order in orders:
            order_id = order.get("AmazonOrderId")
            if not order_id:
                continue
            try:
                item_data = self._api_request("GET", f"/orders/v0/orders/{order_id}/orderItems")
                order["OrderItems"] = item_data.get("payload", {}).get("OrderItems", [])
            except Exception as exc:
                logger.warning("Could not fetch Amazon order items for %s: %s", order_id, exc)
        return {"status": "success", "imported_orders": orders, "imported_count": len(orders), "provider": "AmazonDriver"}

    def handle_webhook(self, headers, payload):
        # Amazon notifications are intentionally persisted first; the periodic
        # order/stock fallback remains authoritative because notifications only
        # contain pointers to the changed resource.
        return {"status": "accepted", "event": payload.get("NotificationType", payload.get("event_type", "unknown")), "provider": "AmazonDriver"}


class FlipkartDriver(MockBaseDriver):
    pass


class MyntraDriver(MockBaseDriver):
    pass


class ShopifyDriver(MockBaseDriver):
    pass


class WooCommerceDriver(MockBaseDriver):
    pass


class EbayDriver(MockBaseDriver):
    pass


class BolDriver(MockBaseDriver):
    pass


class KauflandDriver(MockBaseDriver):
    pass


# Registry Mapping
DRIVER_REGISTRY = {
    "amazon": AmazonDriver,
    "flipkart": FlipkartDriver,
    "myntra": MyntraDriver,
    "shopify": ShopifyDriver,
    "woocommerce": WooCommerceDriver,
    "ebay": EbayDriver,
    "bol.com": BolDriver,
    "kaufland": KauflandDriver,
}


def get_driver(connection) -> BaseMarketplaceDriver:
    connector_type = connection.connector.connector_type.lower()
    driver_class = DRIVER_REGISTRY.get(connector_type)
    if not driver_class:
        # Extensible fallback for future connectors
        return MockBaseDriver(connection)
    return driver_class(connection)
