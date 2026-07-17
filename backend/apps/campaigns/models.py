from django.db import models
from apps.common.models import BaseModel

class Campaign(BaseModel):
    SOURCE_FACEBOOK = 'facebook'
    SOURCE_INSTAGRAM = 'instagram'
    SOURCE_WHATSAPP = 'whatsapp'
    SOURCE_GOOGLE_ADS = 'google_ads'
    SOURCE_EMAIL = 'email'
    SOURCE_YOUTUBE = 'youtube'
    SOURCE_LINKEDIN = 'linkedin'
    SOURCE_DIRECT = 'direct'
    
    SOURCE_CHOICES = [
        (SOURCE_FACEBOOK, 'Facebook'),
        (SOURCE_INSTAGRAM, 'Instagram'),
        (SOURCE_WHATSAPP, 'WhatsApp'),
        (SOURCE_GOOGLE_ADS, 'Google Ads'),
        (SOURCE_EMAIL, 'Email'),
        (SOURCE_YOUTUBE, 'YouTube'),
        (SOURCE_LINKEDIN, 'LinkedIn'),
        (SOURCE_DIRECT, 'Direct'),
    ]

    retailer = models.ForeignKey("retailers.Retailer", on_delete=models.CASCADE, related_name="campaigns")
    name = models.CharField(max_length=255)
    source = models.CharField(max_length=50, choices=SOURCE_CHOICES, default=SOURCE_DIRECT)
    utm_source = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=100, blank=True)
    utm_term = models.CharField(max_length=100, blank=True)
    utm_content = models.CharField(max_length=100, blank=True)
    
    target_url = models.URLField(max_length=2000, help_text="Original URL before UTMs")
    generated_url = models.URLField(max_length=2000, blank=True)
    
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} - {self.retailer.name}"


class CampaignTrackingEvent(BaseModel):
    EVENT_VISIT = 'visit'
    EVENT_PRODUCT_VIEW = 'product_view'
    EVENT_ADD_TO_CART = 'add_to_cart'
    EVENT_CHECKOUT = 'checkout'
    EVENT_PURCHASE = 'purchase'
    
    EVENT_CHOICES = [
        (EVENT_VISIT, 'Visit'),
        (EVENT_PRODUCT_VIEW, 'Product View'),
        (EVENT_ADD_TO_CART, 'Add to Cart'),
        (EVENT_CHECKOUT, 'Checkout'),
        (EVENT_PURCHASE, 'Purchase'),
    ]

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=50, choices=EVENT_CHOICES)
    
    # Context IDs
    product = models.ForeignKey("catalog.Product", on_delete=models.SET_NULL, null=True, blank=True, related_name="campaign_events")
    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="campaign_events")
    
    # Financial impact
    monetary_value = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Visitor tracking
    session_id = models.CharField(max_length=255, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    def __str__(self):
        return f"{self.campaign.name} - {self.event_type}"
