from django import forms

from apps.catalog.models import Category
from apps.settings_app.models import SaleCountdownSetting


class SaleCountdownSettingForm(forms.ModelForm):
    class Meta:
        model = SaleCountdownSetting
        fields = ("retailer", "category", "message", "ends_at", "is_active")
        widgets = {
            "ends_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local", "class": "ra-input"},
            ),
        }

    def __init__(self, *args, retailer=None, admin=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(is_active=True).order_by("name")
        self.fields["ends_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]
        if admin:
            self.fields["retailer"].required = False
            self.fields["retailer"].empty_label = "Global platform setting"
        else:
            self.fields.pop("retailer")
            self.fields.pop("message", None)
            self.fields["category"].required = False
            self.fields["category"].empty_label = "All categories (retailer default)"
            self.retailer = retailer


class RetailerSaleCountdownSettingForm(SaleCountdownSettingForm):
    def __init__(self, *args, retailer=None, **kwargs):
        super().__init__(*args, retailer=retailer, admin=False, **kwargs)

    def save(self, commit=True):
        setting = super().save(commit=False)
        setting.retailer = self.retailer
        # Retailers choose scope and end time only; the sale message is
        # controlled by the admin/global rule.
        setting.message = ""
        if commit:
            setting.save()
        return setting
