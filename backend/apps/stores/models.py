from decimal import Decimal

from django.db import models
from django.db.models import Avg

from apps.common.models import BaseModel


class Store(BaseModel):
    STATUS_DRAFT = "draft"
    STATUS_ACTIVE = "active"
    STATUS_SUSPENDED = "suspended"

    retailer = models.ForeignKey("retailers.Retailer", related_name="stores", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    logo = models.ImageField(upload_to="stores/logos/", blank=True)
    banner = models.ImageField(upload_to="stores/banners/", blank=True)
    icon = models.ImageField(upload_to="stores/icons/", blank=True)
    description = models.TextField(blank=True)
    store_page_tagline = models.CharField(max_length=255, blank=True)
    store_page_announcement = models.CharField(max_length=255, blank=True)
    store_page_sections = models.JSONField(default=list, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=32, blank=True)
    contact_whatsapp = models.CharField(max_length=32, blank=True)
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=32, blank=True)
    country_code = models.CharField(max_length=2, default="DE")
    currency_code = models.CharField(max_length=3, default="EUR", help_text="e.g., EUR, USD, INR")
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    x_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)
    website_url = models.URLField(blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    average_delivery_days = models.PositiveIntegerField(default=3)
    status = models.CharField(max_length=32, default=STATUS_DRAFT)

    @property
    def retailer_label(self) -> str:
        return self.retailer.display_name or self.retailer.legal_name or str(self.retailer)

    @property
    def store_modules_count(self) -> int:
        return len(self.store_page_sections or [])

    def __str__(self) -> str:
        return self.name


class StoreRating(BaseModel):
    store = models.ForeignKey(Store, related_name="ratings", on_delete=models.CASCADE)
    reviewer_name = models.CharField(max_length=120)
    rating = models.PositiveSmallIntegerField(default=5)
    comment = models.TextField(blank=True)
    is_approved = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.store.name} - {self.rating} stars"

    @classmethod
    def refresh_store_average(cls, store):
        """Keep the public store score limited to live, approved ratings."""
        average = cls.objects.filter(
            store=store,
            is_active=True,
            is_approved=True,
        ).aggregate(value=Avg("rating"))["value"] or 0
        store.rating = Decimal(str(round(float(average), 2)))
        store.save(update_fields=["rating", "updated_at"])
