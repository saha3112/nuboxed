from django import forms
from .models import OrderWorkflowGlobalSetting, OrderWorkflowSetting, OrderWorkflowStoreOverride
from apps.users.models import UserAddress, UserPaymentMethod


COUNTRY_CHOICES = (
    ("AD", "Andorra"),
    ("AE", "United Arab Emirates"),
    ("AF", "Afghanistan"),
    ("AG", "Antigua & Barbuda"),
    ("AI", "Anguilla"),
    ("AL", "Albania"),
    ("AM", "Armenia"),
    ("AO", "Angola"),
    ("AQ", "Antarctica"),
    ("AR", "Argentina"),
    ("AS", "Samoa (American)"),
    ("AT", "Austria"),
    ("AU", "Australia"),
    ("AW", "Aruba"),
    ("AX", "Åland Islands"),
    ("AZ", "Azerbaijan"),
    ("BA", "Bosnia & Herzegovina"),
    ("BB", "Barbados"),
    ("BD", "Bangladesh"),
    ("BE", "Belgium"),
    ("BF", "Burkina Faso"),
    ("BG", "Bulgaria"),
    ("BH", "Bahrain"),
    ("BI", "Burundi"),
    ("BJ", "Benin"),
    ("BL", "St Barthelemy"),
    ("BM", "Bermuda"),
    ("BN", "Brunei"),
    ("BO", "Bolivia"),
    ("BQ", "Caribbean NL"),
    ("BR", "Brazil"),
    ("BS", "Bahamas"),
    ("BT", "Bhutan"),
    ("BV", "Bouvet Island"),
    ("BW", "Botswana"),
    ("BY", "Belarus"),
    ("BZ", "Belize"),
    ("CA", "Canada"),
    ("CC", "Cocos (Keeling) Islands"),
    ("CD", "Congo (Dem. Rep.)"),
    ("CF", "Central African Rep."),
    ("CG", "Congo (Rep.)"),
    ("CH", "Switzerland"),
    ("CI", "Côte d’Ivoire"),
    ("CK", "Cook Islands"),
    ("CL", "Chile"),
    ("CM", "Cameroon"),
    ("CN", "China"),
    ("CO", "Colombia"),
    ("CR", "Costa Rica"),
    ("CU", "Cuba"),
    ("CV", "Cape Verde"),
    ("CW", "Curaçao"),
    ("CX", "Christmas Island"),
    ("CY", "Cyprus"),
    ("CZ", "Czech Republic"),
    ("DE", "Germany"),
    ("DJ", "Djibouti"),
    ("DK", "Denmark"),
    ("DM", "Dominica"),
    ("DO", "Dominican Republic"),
    ("DZ", "Algeria"),
    ("EC", "Ecuador"),
    ("EE", "Estonia"),
    ("EG", "Egypt"),
    ("EH", "Western Sahara"),
    ("ER", "Eritrea"),
    ("ES", "Spain"),
    ("ET", "Ethiopia"),
    ("FI", "Finland"),
    ("FJ", "Fiji"),
    ("FK", "Falkland Islands"),
    ("FM", "Micronesia"),
    ("FO", "Faroe Islands"),
    ("FR", "France"),
    ("GA", "Gabon"),
    ("GB", "Britain (UK)"),
    ("GD", "Grenada"),
    ("GE", "Georgia"),
    ("GF", "French Guiana"),
    ("GG", "Guernsey"),
    ("GH", "Ghana"),
    ("GI", "Gibraltar"),
    ("GL", "Greenland"),
    ("GM", "Gambia"),
    ("GN", "Guinea"),
    ("GP", "Guadeloupe"),
    ("GQ", "Equatorial Guinea"),
    ("GR", "Greece"),
    ("GS", "South Georgia & the South Sandwich Islands"),
    ("GT", "Guatemala"),
    ("GU", "Guam"),
    ("GW", "Guinea-Bissau"),
    ("GY", "Guyana"),
    ("HK", "Hong Kong"),
    ("HM", "Heard Island & McDonald Islands"),
    ("HN", "Honduras"),
    ("HR", "Croatia"),
    ("HT", "Haiti"),
    ("HU", "Hungary"),
    ("ID", "Indonesia"),
    ("IE", "Ireland"),
    ("IL", "Israel"),
    ("IM", "Isle of Man"),
    ("IN", "India"),
    ("IO", "British Indian Ocean Territory"),
    ("IQ", "Iraq"),
    ("IR", "Iran"),
    ("IS", "Iceland"),
    ("IT", "Italy"),
    ("JE", "Jersey"),
    ("JM", "Jamaica"),
    ("JO", "Jordan"),
    ("JP", "Japan"),
    ("KE", "Kenya"),
    ("KG", "Kyrgyzstan"),
    ("KH", "Cambodia"),
    ("KI", "Kiribati"),
    ("KM", "Comoros"),
    ("KN", "St Kitts & Nevis"),
    ("KP", "Korea (North)"),
    ("KR", "Korea (South)"),
    ("KW", "Kuwait"),
    ("KY", "Cayman Islands"),
    ("KZ", "Kazakhstan"),
    ("LA", "Laos"),
    ("LB", "Lebanon"),
    ("LC", "St Lucia"),
    ("LI", "Liechtenstein"),
    ("LK", "Sri Lanka"),
    ("LR", "Liberia"),
    ("LS", "Lesotho"),
    ("LT", "Lithuania"),
    ("LU", "Luxembourg"),
    ("LV", "Latvia"),
    ("LY", "Libya"),
    ("MA", "Morocco"),
    ("MC", "Monaco"),
    ("MD", "Moldova"),
    ("ME", "Montenegro"),
    ("MF", "St Martin (French)"),
    ("MG", "Madagascar"),
    ("MH", "Marshall Islands"),
    ("MK", "North Macedonia"),
    ("ML", "Mali"),
    ("MM", "Myanmar (Burma)"),
    ("MN", "Mongolia"),
    ("MO", "Macau"),
    ("MP", "Northern Mariana Islands"),
    ("MQ", "Martinique"),
    ("MR", "Mauritania"),
    ("MS", "Montserrat"),
    ("MT", "Malta"),
    ("MU", "Mauritius"),
    ("MV", "Maldives"),
    ("MW", "Malawi"),
    ("MX", "Mexico"),
    ("MY", "Malaysia"),
    ("MZ", "Mozambique"),
    ("NA", "Namibia"),
    ("NC", "New Caledonia"),
    ("NE", "Niger"),
    ("NF", "Norfolk Island"),
    ("NG", "Nigeria"),
    ("NI", "Nicaragua"),
    ("NL", "Netherlands"),
    ("NO", "Norway"),
    ("NP", "Nepal"),
    ("NR", "Nauru"),
    ("NU", "Niue"),
    ("NZ", "New Zealand"),
    ("OM", "Oman"),
    ("PA", "Panama"),
    ("PE", "Peru"),
    ("PF", "French Polynesia"),
    ("PG", "Papua New Guinea"),
    ("PH", "Philippines"),
    ("PK", "Pakistan"),
    ("PL", "Poland"),
    ("PM", "St Pierre & Miquelon"),
    ("PN", "Pitcairn"),
    ("PR", "Puerto Rico"),
    ("PS", "Palestine"),
    ("PT", "Portugal"),
    ("PW", "Palau"),
    ("PY", "Paraguay"),
    ("QA", "Qatar"),
    ("RE", "Réunion"),
    ("RO", "Romania"),
    ("RS", "Serbia"),
    ("RU", "Russia"),
    ("RW", "Rwanda"),
    ("SA", "Saudi Arabia"),
    ("SB", "Solomon Islands"),
    ("SC", "Seychelles"),
    ("SD", "Sudan"),
    ("SE", "Sweden"),
    ("SG", "Singapore"),
    ("SH", "St Helena"),
    ("SI", "Slovenia"),
    ("SJ", "Svalbard & Jan Mayen"),
    ("SK", "Slovakia"),
    ("SL", "Sierra Leone"),
    ("SM", "San Marino"),
    ("SN", "Senegal"),
    ("SO", "Somalia"),
    ("SR", "Suriname"),
    ("SS", "South Sudan"),
    ("ST", "Sao Tome & Principe"),
    ("SV", "El Salvador"),
    ("SX", "St Maarten (Dutch)"),
    ("SY", "Syria"),
    ("SZ", "Eswatini (Swaziland)"),
    ("TC", "Turks & Caicos Is"),
    ("TD", "Chad"),
    ("TF", "French S. Terr."),
    ("TG", "Togo"),
    ("TH", "Thailand"),
    ("TJ", "Tajikistan"),
    ("TK", "Tokelau"),
    ("TL", "East Timor"),
    ("TM", "Turkmenistan"),
    ("TN", "Tunisia"),
    ("TO", "Tonga"),
    ("TR", "Turkey"),
    ("TT", "Trinidad & Tobago"),
    ("TV", "Tuvalu"),
    ("TW", "Taiwan"),
    ("TZ", "Tanzania"),
    ("UA", "Ukraine"),
    ("UG", "Uganda"),
    ("UM", "US minor outlying islands"),
    ("US", "United States"),
    ("UY", "Uruguay"),
    ("UZ", "Uzbekistan"),
    ("VA", "Vatican City"),
    ("VC", "St Vincent"),
    ("VE", "Venezuela"),
    ("VG", "Virgin Islands (UK)"),
    ("VI", "Virgin Islands (US)"),
    ("VN", "Vietnam"),
    ("VU", "Vanuatu"),
    ("WF", "Wallis & Futuna"),
    ("WS", "Samoa (western)"),
    ("YE", "Yemen"),
    ("YT", "Mayotte"),
    ("ZA", "South Africa"),
    ("ZM", "Zambia"),
    ("ZW", "Zimbabwe"),
)


def build_payment_method_choices():
    return (("card", "Credit / debit card"), ("cod", "Cash on delivery"), ("bank_transfer", "Bank transfer"))


# Payment methods exposed by the payment-options form.  UPI is country-specific;
# the other methods are kept available where the application has no provider
# restriction configured yet.
PAYMENT_METHODS_BY_COUNTRY = {
    "IN": ("card", "upi", "bank", "wallet"),
}


def payment_method_types_for_country(country_code):
    country_code = (country_code or "").upper()
    allowed = PAYMENT_METHODS_BY_COUNTRY.get(country_code, ("card", "bank", "wallet"))
    return tuple((value, label) for value, label in UserPaymentMethod.TYPE_CHOICES if value in allowed)


class UserAddressForm(forms.ModelForm):
    label = forms.ChoiceField(
        label="Address type",
        choices=(("Home", "Home"), ("Work", "Work"), ("Other", "Other")),
        widget=forms.RadioSelect(attrs={"class": "address-type-options"}),
    )
    country_code = forms.ChoiceField(
        label="Country",
        choices=COUNTRY_CHOICES,
        widget=forms.Select(attrs={"autocomplete": "country", "data-country-select": "true"}),
    )

    class Meta:
        model = UserAddress
        fields = ("label", "full_name", "phone", "country_code", "city", "state", "postal_code", "address_line1", "address_line2", "landmark", "is_default")
        labels = {
            "postal_code": "Postal code",
            "address_line1": "Address line 1",
            "address_line2": "Address line 2",
            "landmark": "Landmark",
        }
        widgets = {
            "city": forms.TextInput(attrs={"autocomplete": "address-level2", "data-city-field": "true"}),
            "state": forms.TextInput(attrs={"autocomplete": "address-level1", "data-state-field": "true"}),
            "postal_code": forms.TextInput(attrs={"autocomplete": "postal-code", "data-postal-field": "true"}),
            "address_line1": forms.TextInput(attrs={"autocomplete": "address-line1"}),
            "address_line2": forms.TextInput(attrs={"autocomplete": "address-line2"}),
            "landmark": forms.TextInput(attrs={"autocomplete": "address-line3", "placeholder": "Nearby landmark (optional)"}),
        }


class UserPaymentMethodForm(forms.ModelForm):
    country_code = forms.ChoiceField(
        label="Country",
        choices=COUNTRY_CHOICES,
        widget=forms.Select(attrs={"autocomplete": "country", "data-payment-country": "true"}),
    )

    def __init__(self, *args, country_code=None, **kwargs):
        super().__init__(*args, **kwargs)
        selected_country = country_code or self.data.get(self.add_prefix("country_code")) or self.initial.get("country_code") or "DE"
        self.fields["method_type"].choices = payment_method_types_for_country(selected_country)
        self.fields["method_type"].widget.attrs["data-payment-method"] = "true"

    def clean(self):
        cleaned = super().clean()
        country = cleaned.get("country_code")
        method_type = cleaned.get("method_type")
        allowed = {value for value, _ in payment_method_types_for_country(country)}
        if method_type and method_type not in allowed:
            self.add_error("method_type", "This payment method is not supported in the selected country.")
        return cleaned

    class Meta:
        model = UserPaymentMethod
        fields = ("country_code", "method_type", "display_name", "last4", "expiry", "is_default")
        widgets = {
            "method_type": forms.Select(),
            "display_name": forms.TextInput(attrs={"placeholder": "e.g. Visa ending in 1234"}),
            "last4": forms.TextInput(attrs={"maxlength": 4, "inputmode": "numeric", "placeholder": "Last 4 digits (optional)"}),
            "expiry": forms.TextInput(attrs={"placeholder": "MM/YYYY (optional)"}),
            "is_default": forms.CheckboxInput(),
        }


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


class _OrderWorkflowFieldsForm(forms.ModelForm):
    class Meta:
        fields = ("auto_invoice", "allow_manual_invoice", "auto_label", "allow_manual_label", "notify_customer_order_placed", "notify_customer_status_changed")
        widgets = {field: forms.CheckboxInput(attrs={"class": "ra-checkbox"}) for field in fields}


class OrderWorkflowGlobalSettingForm(_OrderWorkflowFieldsForm):
    class Meta(_OrderWorkflowFieldsForm.Meta):
        model = OrderWorkflowGlobalSetting


class OrderWorkflowStoreOverrideForm(_OrderWorkflowFieldsForm):
    is_active = forms.BooleanField(required=False, label="Use custom settings for this store", widget=forms.CheckboxInput(attrs={"class": "ra-checkbox"}))

    class Meta(_OrderWorkflowFieldsForm.Meta):
        model = OrderWorkflowStoreOverride
        fields = ("is_active",) + _OrderWorkflowFieldsForm.Meta.fields


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
