from django import forms
from .models import OrderWorkflowSetting
from apps.users.models import UserAddress


def build_payment_method_choices():
    return (("card", "Credit / debit card"), ("cod", "Cash on delivery"), ("bank_transfer", "Bank transfer"))


class UserAddressForm(forms.ModelForm):
    class Meta:
        model = UserAddress
        fields = ("label", "full_name", "phone", "address_line1", "address_line2", "city", "state", "postal_code", "country_code", "is_default")


class CheckoutSelectionForm(forms.Form):
    payment_method = forms.ChoiceField(choices=())
    note = forms.CharField(required=False, widget=forms.Textarea)
    def __init__(self, *args, payment_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment_method"].choices = payment_choices or build_payment_method_choices()


class OrderWorkflowSettingForm(forms.ModelForm):
    class Meta:
        model = OrderWorkflowSetting
        fields = ("auto_invoice", "allow_manual_invoice", "auto_label", "allow_manual_label", "notify_customer_order_placed", "notify_customer_status_changed")
        widgets = {field: forms.CheckboxInput(attrs={"class": "ra-checkbox"}) for field in fields}


class OrderStatusForm(forms.Form):
    status = forms.ChoiceField(choices=())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Order
        self.fields["status"].choices = Order.STATUS_CHOICES


class EmailTemplateForm(forms.ModelForm):
    class Meta:
        from apps.notifications.models import NotificationTemplate
        model = NotificationTemplate
        fields = ("event_name", "channel", "subject_template", "body_template", "is_active")
        widgets = {"body_template": forms.Textarea(attrs={"rows": 10}), "event_name": forms.TextInput(attrs={"placeholder": "order_status_changed"})}
