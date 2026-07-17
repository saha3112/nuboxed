import urllib.parse
from decimal import Decimal
from django.db.models import Sum

from apps.campaigns.models import Campaign, CampaignTrackingEvent

def generate_campaign_link(retailer, name, target_url, source, utm_source='', utm_medium='', utm_campaign='', utm_term='', utm_content=''):
    """
    Generates a campaign with UTM parameters encoded in the generated_url.
    """
    if not utm_source:
        utm_source = source
        
    parsed_url = urllib.parse.urlparse(target_url)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    
    query_params['utm_source'] = [utm_source]
    if utm_medium: query_params['utm_medium'] = [utm_medium]
    if utm_campaign: query_params['utm_campaign'] = [utm_campaign]
    if utm_term: query_params['utm_term'] = [utm_term]
    if utm_content: query_params['utm_content'] = [utm_content]
    
    new_query = urllib.parse.urlencode(query_params, doseq=True)
    generated_url = parsed_url._replace(query=new_query).geturl()
    
    campaign = Campaign.objects.create(
        retailer=retailer,
        name=name,
        source=source,
        utm_source=utm_source,
        utm_medium=utm_medium,
        utm_campaign=utm_campaign,
        utm_term=utm_term,
        utm_content=utm_content,
        target_url=target_url,
        generated_url=generated_url
    )
    return campaign

def track_campaign_event(campaign, event_type, product=None, order=None, monetary_value=Decimal('0.00'), session_id='', ip_address=None, user_agent=''):
    """
    Records a tracking event for a specific campaign.
    """
    event = CampaignTrackingEvent.objects.create(
        campaign=campaign,
        event_type=event_type,
        product=product,
        order=order,
        monetary_value=monetary_value,
        session_id=session_id,
        ip_address=ip_address,
        user_agent=user_agent
    )
    return event

def get_campaign_analytics(retailer, campaign=None):
    """
    Fetches analytics for a specific campaign or all campaigns under a retailer.
    """
    qs = Campaign.objects.filter(retailer=retailer, is_active=True)
    if campaign:
        qs = qs.filter(id=campaign.id)
        
    metrics = {
        'total_visits': CampaignTrackingEvent.objects.filter(campaign__in=qs, event_type=CampaignTrackingEvent.EVENT_VISIT).count(),
        'total_product_views': CampaignTrackingEvent.objects.filter(campaign__in=qs, event_type=CampaignTrackingEvent.EVENT_PRODUCT_VIEW).count(),
        'total_add_to_cart': CampaignTrackingEvent.objects.filter(campaign__in=qs, event_type=CampaignTrackingEvent.EVENT_ADD_TO_CART).count(),
        'total_checkouts': CampaignTrackingEvent.objects.filter(campaign__in=qs, event_type=CampaignTrackingEvent.EVENT_CHECKOUT).count(),
        'total_purchases': CampaignTrackingEvent.objects.filter(campaign__in=qs, event_type=CampaignTrackingEvent.EVENT_PURCHASE).count(),
    }
    
    sales_agg = CampaignTrackingEvent.objects.filter(
        campaign__in=qs, 
        event_type=CampaignTrackingEvent.EVENT_PURCHASE
    ).aggregate(total_sales=Sum('monetary_value'))
    
    metrics['campaign_sales'] = sales_agg['total_sales'] or Decimal('0.00')
    
    if metrics['total_visits'] > 0:
        metrics['conversion_rate'] = round((metrics['total_purchases'] / metrics['total_visits']) * 100, 2)
    else:
        metrics['conversion_rate'] = 0.00
        
    return metrics
