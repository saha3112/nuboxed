from django.db import models

from apps.common.models import BaseModel


class Page(BaseModel):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    content = models.TextField(blank=True)
    is_published = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.title


class Slider(BaseModel):
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=255, blank=True)
    cta_label = models.CharField(max_length=80, blank=True)
    cta_url = models.CharField(max_length=255, blank=True)
    image = models.ImageField(upload_to="sliders/", blank=True)
    status = models.CharField(max_length=32, default="draft")
    sort_order = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return self.title


class FeaturedBanner(BaseModel):
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=255, blank=True)
    link_url = models.CharField(max_length=255, blank=True)
    image = models.ImageField(upload_to="featured-banners/", blank=True)
    status = models.CharField(max_length=32, default="draft")
    placement = models.CharField(max_length=64, default="homepage")

    def __str__(self) -> str:
        return self.title
