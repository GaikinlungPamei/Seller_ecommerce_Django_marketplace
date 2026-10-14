"""Cart, address and coupon forms."""
from django import forms

from .models import Address, Coupon


class AddressForm(forms.ModelForm):
    """Delivery address capture at checkout."""

    class Meta:
        model = Address
        fields = ("full_name", "phone", "line1", "line2", "city", "state", "postal_code")
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "+1 555 010 2233"}),
            "line1": forms.TextInput(attrs={"class": "form-control", "placeholder": "Street, house number"}),
            "line2": forms.TextInput(attrs={"class": "form-control", "placeholder": "Apartment, landmark (optional)"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "state": forms.TextInput(attrs={"class": "form-control"}),
            "postal_code": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        digits = [c for c in phone if c.isdigit()]
        if len(digits) < 7:
            raise forms.ValidationError("Please enter a valid phone number (at least 7 digits).")
        return phone

    def clean_postal_code(self):
        postal_code = (self.cleaned_data.get("postal_code") or "").strip()
        if len(postal_code) < 3:
            raise forms.ValidationError("Please enter a valid postal / ZIP code.")
        return postal_code


class CouponForm(forms.Form):
    """Apply a coupon code at checkout."""

    code = forms.CharField(max_length=40, widget=forms.TextInput(attrs={
        "class": "form-control text-uppercase", "placeholder": "Coupon code",
        "autocomplete": "off",
    }))

    def clean_code(self):
        return (self.cleaned_data.get("code") or "").strip().upper()


class AddressSelectForm(forms.Form):
    """Pick a saved address during checkout."""

    address = forms.ModelChoiceField(
        queryset=Address.objects.none(), required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["address"].queryset = Address.objects.filter(user=user)


class CouponAdminForm(forms.ModelForm):
    class Meta:
        model = Coupon
        fields = ("code", "discount_percent", "min_order", "max_uses", "expires_at", "active")
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control text-uppercase", "placeholder": "WELCOME10"}),
            "discount_percent": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 90}),
            "min_order": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": 0}),
            "max_uses": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "expires_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"class": "form-control", "type": "datetime-local"}),
            "active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_code(self):
        return (self.cleaned_data.get("code") or "").strip().upper()

    def clean_discount_percent(self):
        value = self.cleaned_data["discount_percent"]
        if not 1 <= value <= 90:
            raise forms.ValidationError("Discount must be between 1% and 90%.")
        return value

