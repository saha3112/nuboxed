from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from django.db import transaction
from apps.catalog.forms import ProductAttributeForm, ProductForm
from apps.catalog.models import Category, Product, ProductAttribute
from apps.retailers.forms import StoreForm
from apps.retailers.models import Retailer
from apps.retailers.services import unique_slug
from apps.rbac.constants import ROLE_RETAILER_OWNER
from apps.rbac.constants import DEFAULT_PERMISSIONS
from apps.rbac.models import Permission
from apps.rbac.services import assign_membership_role
from apps.accounts.models import Account, AccountMembership
from apps.users.services import generate_unique_username
from apps.stores.models import Store
from apps.users.models import User
from apps.shipments.models import CourierPartner
from apps.inventory.models import Warehouse


class EmailSettingsForm(forms.Form):
    host = forms.CharField(label="SMTP host", required=False, widget=forms.TextInput(attrs={"placeholder": "smtp.example.com"}))
    port = forms.IntegerField(label="SMTP port", required=False, initial=587, min_value=1, max_value=65535)
    username = forms.CharField(label="SMTP username", required=False)
    password = forms.CharField(label="SMTP password", required=False, widget=forms.PasswordInput(attrs={"placeholder": "Leave blank to keep current password", "autocomplete": "new-password"}))
    use_tls = forms.BooleanField(label="Use TLS", required=False, initial=True)
    use_ssl = forms.BooleanField(label="Use SSL", required=False)
    default_from_email = forms.EmailField(label="Default from email", required=False)
    timeout = forms.IntegerField(label="Connection timeout (seconds)", required=False, initial=30, min_value=1, max_value=300)
    test_recipient = forms.EmailField(label="Test recipient", required=False, widget=forms.EmailInput(attrs={"placeholder": "you@example.com"}))

    def __init__(self, *args, current=None, **kwargs):
        super().__init__(*args, **kwargs)
        current = current or {}
        for name in self.fields:
            if name != "password" and name in current:
                self.fields[name].initial = current[name]
        if current.get("password"):
            self.fields["password"].help_text = "A password is already saved. Leave blank to keep it."

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("use_tls") and cleaned.get("use_ssl"):
            # SSL takes precedence if an older browser/session submits both.
            # The form JavaScript also keeps these checkboxes mutually exclusive.
            cleaned["use_tls"] = False
        return cleaned


class BackofficeLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"autofocus": True, "placeholder": "admin@commerceos.com"}),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"placeholder": "Enter your password"}),
    )

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_super_admin:
            raise forms.ValidationError(
                "Wrong admin details.",
                code="invalid_login",
            )


class BackofficePermissionForm(forms.ModelForm):
    """Feature-based permission selector for the backoffice."""

    feature_permission = forms.ChoiceField(
        label="Feature access",
        choices=(),
        widget=forms.Select(attrs={"class": "feature-permission-select"}),
        help_text="Choose the feature capability to grant. The permission code and display name are generated automatically.",
    )

    class Meta:
        model = Permission
        fields = ["feature_permission", "is_active"]
        labels = {"is_active": "Permission enabled"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(code, name) for code, name in DEFAULT_PERMISSIONS.items()]
        current_code = getattr(self.instance, "code", "")
        if current_code and current_code not in dict(choices):
            choices.append((current_code, getattr(self.instance, "name", current_code)))
        self.fields["feature_permission"].choices = choices
        self.fields["feature_permission"].initial = current_code

    def clean_feature_permission(self):
        code = self.cleaned_data["feature_permission"]
        if Permission.objects.exclude(pk=self.instance.pk).filter(code=code).exists():
            raise forms.ValidationError("This feature permission already exists.")
        return code

    def save(self, commit=True):
        permission = super().save(commit=False)
        code = self.cleaned_data["feature_permission"]
        permission.code = code
        permission.name = DEFAULT_PERMISSIONS.get(code, dict(self.fields["feature_permission"].choices).get(code, code))
        if commit:
            permission.save()
        return permission


class BackofficeUserCreateForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput())

    class Meta:
        model = User
        fields = [
            "email",
            "username",
            "first_name",
            "last_name",
            "phone",
            "password",
            "is_staff",
            "is_active",
            "is_email_verified",
            "otp_enabled",
        ]

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class BackofficeUserUpdateForm(forms.ModelForm):
    new_password = forms.CharField(required=False, widget=forms.PasswordInput())

    class Meta:
        model = User
        fields = [
            "email",
            "username",
            "first_name",
            "last_name",
            "phone",
            "new_password",
            "is_staff",
            "is_active",
            "is_email_verified",
            "otp_enabled",
        ]

    def clean_new_password(self):
        password = self.cleaned_data.get("new_password")
        if password:
            validate_password(password, self.instance)
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("new_password"):
            user.set_password(self.cleaned_data["new_password"])
        if commit:
            user.save()
        return user


class BackofficeRetailerCreateForm(forms.ModelForm):
    email = forms.EmailField(
        label="Login email",
        required=True,
        widget=forms.EmailInput(attrs={"placeholder": "retailer@example.com"}),
    )
    password = forms.CharField(
        label="Login password",
        required=True,
        strip=False,
        widget=forms.PasswordInput(attrs={"placeholder": "Create a secure password"}),
    )
    confirm_password = forms.CharField(label="Re-enter login password", required=True, strip=False, widget=forms.PasswordInput(attrs={"placeholder": "Re-enter the login password"}))

    class Meta:
        model = Retailer
        fields = ["legal_name", "email", "password"]
        labels = {"legal_name": "Retailer name"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["legal_name"].required = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("A user with this email address already exists.")
        return email

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") and cleaned.get("confirm_password") and cleaned["password"] != cleaned["confirm_password"]:
            self.add_error("confirm_password", "The passwords do not match.")
        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        if not commit:
            raise ValueError("Retailer creation requires commit=True.")
        name = self.cleaned_data["legal_name"].strip()
        email = self.cleaned_data["email"]
        user = User.objects.create_user(
            username=generate_unique_username(email),
            email=email,
            password=self.cleaned_data["password"],
            first_name=name,
            is_active=True,
        )
        account = Account.objects.create(
            name=name,
            slug=unique_slug(Account, name),
            owner=user,
        )
        retailer = Retailer.objects.create(
            account=account,
            legal_name=name,
            display_name=name,
            support_email=email,
            status=Retailer.STATUS_APPROVED,
            is_active=True,
        )
        membership = AccountMembership.objects.create(
            account=account,
            user=user,
            title="Retailer Owner",
            status="active",
        )
        assign_membership_role(user, membership, ROLE_RETAILER_OWNER)
        return retailer


class BackofficeRetailerUpdateForm(forms.ModelForm):
    new_password = forms.CharField(
        label="New login password",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"placeholder": "Leave blank to keep current password"}),
        help_text="Set this only when you want to reset the retailer login password.",
    )
    confirm_new_password = forms.CharField(
        label="Re-enter new login password",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"placeholder": "Re-enter the new password"}),
    )

    class Meta:
        model = Retailer
        exclude = ("account", "created_at", "updated_at")

    def clean_new_password(self):
        password = self.cleaned_data.get("new_password")
        if password:
            validate_password(password, self.instance.account.owner)
        return password

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("new_password")
        confirmation = cleaned.get("confirm_new_password")
        if password and password != confirmation:
            self.add_error("confirm_new_password", "The passwords do not match.")
        elif confirmation and not password:
            self.add_error("new_password", "Enter the new password first.")
        return cleaned

    def save(self, commit=True):
        retailer = super().save(commit=commit)
        password = self.cleaned_data.get("new_password")
        if password:
            owner = retailer.account.owner
            owner.set_password(password)
            owner.save(update_fields=["password", "updated_at"])
        return retailer


class BackofficeProductAttributeForm(ProductAttributeForm):
    color_values_payload = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )

    class Meta(ProductAttributeForm.Meta):
        model = ProductAttribute


class BackofficeCategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "slug", "parent", "sort_order", "description", "seo_title", "seo_description", "is_featured", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["parent"].queryset = Category.objects.filter(is_active=True).select_related("parent").order_by("parent__name", "sort_order", "name")
        self.fields["parent"].required = False
        self.fields["parent"].label_from_instance = lambda obj: f"{obj.parent.name} / {obj.name}" if obj.parent_id and obj.parent else obj.name
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                continue
            field.widget.attrs.setdefault("class", "bo-product-input")


class BackofficeProductForm(ProductForm):
    retailer = forms.ModelChoiceField(
        queryset=Retailer.objects.none(),
        required=True,
        label="Retailer",
    )
    # Declare these explicitly as this form has its own dynamically extended
    # field set; otherwise Django's ModelForm metaclass can omit the newly
    # added Product model fields from the backoffice form.
    sale_title = forms.CharField(
        required=False,
        label="Sale message",
        widget=forms.TextInput(attrs={"placeholder": "Hurry up! Sale ends in:"}),
    )
    sale_ends_at = forms.DateTimeField(
        required=False,
        label="Sale ends at",
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local"},
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dynamic_attribute_field_names = [
            field_name for field_name in self.fields if field_name.startswith("attr_")
        ]
        self.fields["retailer"].queryset = Retailer.objects.filter(is_active=True).order_by("legal_name", "display_name")
        self.fields["retailer"].widget.attrs.update({
            "class": "bo-product-input",
            "data-admin-retailer-select": "true",
        })
        self.fields["store"].required = True
        store_queryset = Store.objects.filter(
            retailer__is_active=True,
        ).select_related("retailer").order_by("retailer__legal_name", "name", "-created_at")
        # Keep the product's existing store selectable during edits even when
        # that store is now draft/inactive; otherwise the edit form silently
        # drops the stored relation and admin/retailer data diverges.
        if self.instance and getattr(self.instance, "store_id", None):
            store_queryset = Store.objects.filter(
                Q(id__in=store_queryset.values("id")) | Q(id=self.instance.store_id)
            ).select_related("retailer").order_by("retailer__legal_name", "name", "-created_at")
        self.fields["store"].queryset = store_queryset
        self.fields["store"].widget.attrs.update({
            "class": "bo-product-input",
            "data-admin-store-select": "true",
        })
        selected_retailer_id = (
            self.data.get("retailer")
            if self.is_bound
            else self.initial.get("retailer") or getattr(self.instance, "retailer_id", None)
        )
        if selected_retailer_id:
            self.fields["store"].queryset = self.fields["store"].queryset.filter(retailer_id=selected_retailer_id)
        elif self.instance and getattr(self.instance, "store_id", None):
            self.fields["store"].queryset = self.fields["store"].queryset.filter(retailer_id=self.instance.store.retailer_id)
        else:
            self.fields["store"].queryset = self.fields["store"].queryset.none()
        self.fields["store"].label_from_instance = self._store_label
        if self.instance and getattr(self.instance, "retailer_id", None):
            self.fields["retailer"].initial = self.instance.retailer
        if self.instance and getattr(self.instance, "store_id", None):
            self.fields["store"].initial = self.instance.store
        self.admin_store_picker_json = [
            {
                "id": str(store.id),
                "name": self._store_label(store),
                "retailer_id": str(store.retailer_id),
                "status": store.status,
                "is_active": store.is_active,
            }
            for store in store_queryset
        ]
        for field_name in ("price", "discount_price", "product_video_urls"):
            if field_name in self.fields:
                self.fields[field_name].widget = forms.HiddenInput()
                self.fields[field_name].required = False
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                continue
            field.widget.attrs.setdefault("class", "bo-product-input")
        self.fields["description"].widget.attrs.setdefault("rows", 6)

    def _store_label(self, store):
        state = []
        if getattr(store, "status", ""):
            state.append(store.status.title())
        if not getattr(store, "is_active", True):
            state.append("Inactive")
        suffix = f" ({', '.join(state)})" if state else ""
        return f"{store.name}{suffix}"

    def clean(self):
        cleaned = super().clean()
        retailer = cleaned.get("retailer")
        store = cleaned.get("store")
        if not retailer:
            raise ValidationError({"retailer": "Choose a retailer before assigning a store."})
        if not store:
            raise ValidationError({"store": "Choose a store for this retailer."})
        if store.retailer_id != retailer.id:
            raise ValidationError({"store": "Choose a store that belongs to the selected retailer."})
        return cleaned

    def save(self, commit=True):
        product = super().save(commit=False)
        product.retailer = self.cleaned_data["retailer"]
        product.store = self.cleaned_data["store"]
        phone_variant = self.resolve_phone_variant_from_payload()
        product.phone_variant = phone_variant
        product.sync_phone_identity()
        if commit:
            product.save()
            self.save_product_attributes(product)
            self.sync_product_variants(product)
        return product

    class Meta(ProductForm.Meta):
        model = Product
        fields = [
            "retailer", "store", "category", "brand",
            "name", "model_name",
            "short_description", "description",
            "price", "discount_price", "sale_title", "sale_ends_at", "sale_override_enabled", "tax_rate",
            "product_type",
            "weight", "length", "width", "height",
            "warranty",
            "is_featured", "is_active",
        ]


class BackofficeStoreForm(StoreForm):
    retailer_name = forms.CharField(
        required=False,
        label="Retailer name",
        widget=forms.TextInput(attrs={"class": "ra-input", "placeholder": "Retailer name"}),
    )
    retailer = forms.ModelChoiceField(
        queryset=Retailer.objects.none(),
        required=True,
        label="Retailer",
    )
    status = forms.ChoiceField(
        choices=(
            (Store.STATUS_DRAFT, "Draft"),
            (Store.STATUS_ACTIVE, "Active"),
            (Store.STATUS_SUSPENDED, "Suspended"),
        ),
        initial=Store.STATUS_DRAFT,
        label="Status",
    )

    class Meta(StoreForm.Meta):
        model = Store
        exclude = ("slug", "is_active", "created_at", "updated_at", "icon", "store_page_sections")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["retailer"].queryset = Retailer.objects.filter(is_active=True).order_by("legal_name", "display_name")
        self.fields["retailer"].widget.attrs.update({"class": "ra-input"})
        if self.instance and getattr(self.instance, "retailer_id", None):
            self.fields["retailer"].initial = self.instance.retailer
            self.fields["retailer_name"].initial = self.instance.retailer.display_name or self.instance.retailer.legal_name
            self.fields["retailer_name"].required = True
            self.fields["retailer"].widget = forms.HiddenInput()
        if "status" in self.fields:
            self.fields["status"].widget.attrs.setdefault("class", "ra-input")

    def save(self, commit=True):
        store = super().save(commit=False)
        store.retailer = self.cleaned_data["retailer"]
        retailer_name = (self.cleaned_data.get("retailer_name") or "").strip()
        if retailer_name and store.retailer:
            retailer = store.retailer
            old_display_name = retailer.display_name
            retailer.display_name = retailer_name
            if not retailer.legal_name or retailer.legal_name == old_display_name:
                retailer.legal_name = retailer_name
            retailer.save(update_fields=["display_name", "legal_name", "updated_at"])
        store.is_active = store.status == Store.STATUS_ACTIVE
        if not store.slug:
            store.slug = unique_slug(Store, store.name)
        if commit:
            store.save()
            if store.retailer.account_id and store.retailer.account.owner_id:
                from apps.accounts.models import AccountMembership

                AccountMembership.objects.update_or_create(
                    account=store.retailer.account,
                    user=store.retailer.account.owner,
                    defaults={
                        "store": None,
                        "title": "Retailer Owner",
                        "status": "active",
                        "is_active": True,
                    },
                )
        return store


class BackofficeAttributeOptionsForm(forms.Form):
    options_payload = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )


class CourierPartnerForm(forms.ModelForm):
    class Meta:
        model = CourierPartner
        fields = ['name', 'code', 'service_regions', 'status']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-field',
                'placeholder': 'e.g., DHL Express, FedEx, Local Courier',
                'required': True,
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-field',
                'placeholder': 'e.g., dhl, fedex, local',
                'required': True,
            }),
            'service_regions': forms.Textarea(attrs={
                'class': 'form-field',
                'rows': 3,
                'placeholder': 'Service regions (comma-separated) e.g., India, USA, EU',
            }),
            'status': forms.Select(attrs={
                'class': 'form-field',
            }),
        }

    def clean_code(self):
        code = self.cleaned_data['code'].strip().lower()
        if len(code) < 2:
            raise forms.ValidationError("Code must be at least 2 characters")
        return code

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if len(name) < 2:
            raise forms.ValidationError("Name must be at least 2 characters")
        return name


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ['name', 'code', 'retailer', 'store', 'address_line1', 'address_line2',
                  'city', 'state', 'postal_code', 'country_code', 'delivery_days',
                  'handling_time_days', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-field',
                'placeholder': 'e.g., Main Warehouse, Delhi Distribution Center',
                'required': True,
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-field',
                'placeholder': 'e.g., WH001, DELHI-DC',
                'required': True,
            }),
            'retailer': forms.Select(attrs={
                'class': 'form-field',
                'required': True,
            }),
            'store': forms.Select(attrs={
                'class': 'form-field',
                'required': False,
            }),
            'address_line1': forms.TextInput(attrs={
                'class': 'form-field',
                'placeholder': 'Street address',
            }),
            'address_line2': forms.TextInput(attrs={
                'class': 'form-field',
                'placeholder': 'Apartment, suite, etc. (optional)',
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-field',
                'placeholder': 'City',
            }),
            'state': forms.TextInput(attrs={
                'class': 'form-field',
                'placeholder': 'State/Province',
            }),
            'postal_code': forms.TextInput(attrs={
                'class': 'form-field',
                'placeholder': 'Postal code',
            }),
            'country_code': forms.TextInput(attrs={
                'class': 'form-field',
                'placeholder': 'e.g., IN, US, DE',
                'maxlength': '2',
            }),
            'delivery_days': forms.NumberInput(attrs={
                'class': 'form-field',
                'min': '1',
                'placeholder': 'Days for delivery',
            }),
            'handling_time_days': forms.NumberInput(attrs={
                'class': 'form-field',
                'min': '0',
                'placeholder': 'Days for processing',
            }),
            'is_default': forms.CheckboxInput(attrs={
                'class': 'form-field',
            }),
        }

    def clean_code(self):
        code = self.cleaned_data['code'].strip().upper()
        if len(code) < 2:
            raise forms.ValidationError("Code must be at least 2 characters")
        return code

    def clean_country_code(self):
        code = self.cleaned_data['country_code'].strip().upper()
        if len(code) != 2:
            raise forms.ValidationError("Country code must be 2 characters (ISO 3166-1)")
        return code

    def clean_delivery_days(self):
        days = self.cleaned_data['delivery_days']
        if days < 1:
            raise forms.ValidationError("Delivery days must be at least 1")
        return days
