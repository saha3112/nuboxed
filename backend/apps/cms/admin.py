from django.contrib import admin

from .models import FeaturedBanner, Page, Slider

admin.site.register(Page)
admin.site.register(Slider)
admin.site.register(FeaturedBanner)
