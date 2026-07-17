from django.db import models

from apps.common.models import BaseModel


class ReportJob(BaseModel):
    code = models.CharField(max_length=100)
    status = models.CharField(max_length=32, default="queued")
    payload = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return self.code
