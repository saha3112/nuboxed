from django.contrib import admin

from .models import (
    CourierBooking,
    CourierCredential,
    CourierCountryServiceability,
    CourierPartner,
    CourierPerformanceReport,
    CourierPickupSchedule,
    CourierRule,
    CourierReturnPickup,
    CourierServiceabilityRule,
    CourierShipmentEvent,
    FulfillmentRecord,
    Shipment,
)

admin.site.register(Shipment)
admin.site.register(CourierPartner)
admin.site.register(CourierBooking)
admin.site.register(CourierCredential)
admin.site.register(CourierCountryServiceability)
admin.site.register(CourierServiceabilityRule)
admin.site.register(CourierRule)
admin.site.register(CourierShipmentEvent)
admin.site.register(CourierPickupSchedule)
admin.site.register(CourierReturnPickup)
admin.site.register(CourierPerformanceReport)
admin.site.register(FulfillmentRecord)
