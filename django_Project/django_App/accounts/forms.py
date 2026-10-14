"""Authentication and profile forms."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm, UserCreationForm
)

User = get_user_model()

WIDGETS = {
    "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "you@example.com"}),
    "text": forms.TextInput(attrs={"class": "form-control"}),
    "password": forms.PasswordInput(attrs={"class": "form-control", "placeholder": "••••••••"}),
}


class CustomerRegisterForm(UserCreationForm):
    """Customer registration using Email and Password."""

    first_name = forms.CharField(max_length=80, widget=WIDGETS["text"], label="First name")
    last_name = forms.CharField(max_length=80, required=False, widget=WIDGETS["text"], label="Last name")
    email = forms.EmailField(widget=WIDGETS["email"], label="Email address")

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update(WIDGETS["password"].attrs)
        self.fields["password2"].widget.attrs.update(WIDGETS["password"].attrs)
        for name in ("first_name", "last_name", "email"):
            self.fields[name].widget.attrs.setdefault("class", "form-control")

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if not email:
            raise forms.ValidationError("Please provide an email address.")
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("An account with this email address already exists. Please sign in instead.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        email = self.cleaned_data["email"].strip().lower()
        user.email = email
        user.username = email
        user.role = User.Role.CUSTOMER
        user.status = User.Status.ACTIVE
        if commit:
            user.save()
        return user


class SellerRegisterForm(CustomerRegisterForm):
    """Seller registration using Email, Password and Shop name."""

    shop_name = forms.CharField(max_length=120, widget=WIDGETS["text"], label="Shop name")

    class Meta(CustomerRegisterForm.Meta):
        fields = ("first_name", "last_name", "email", "shop_name")

    def clean_shop_name(self):
        shop = self.cleaned_data.get("shop_name", "").strip()
        if not shop:
            raise forms.ValidationError("Please provide your Shop name.")
        return shop

    def save(self, commit=True):
        user = super().save(commit=False)
        email = self.cleaned_data["email"].strip().lower()
        user.email = email
        user.username = email
        user.shop_name = self.cleaned_data["shop_name"]
        user.role = User.Role.SELLER
        user.status = User.Status.PENDING  # requires admin approval
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    """Sign-in form using Email and Password."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email address"
        self.fields["username"].widget.attrs.update(
            {"class": "form-control", "placeholder": "you@gmail.com", "autofocus": True}
        )
        self.fields["password"].widget.attrs.update(
            {"class": "form-control", "placeholder": "••••••••"}
        )


class ProfileForm(forms.ModelForm):
    """Profile management for all three roles."""

    email = forms.EmailField(widget=WIDGETS["email"])

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone", "shop_name")
        widgets = {
            "first_name": WIDGETS["text"],
            "last_name": WIDGETS["text"],
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "+1 555 010 2233"}),
            "shop_name": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.role != User.Role.SELLER:
            del self.fields["shop_name"]


class ResetPasswordForm(PasswordChangeForm):
    """Reset / change password."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("old_password", "new_password1", "new_password2"):
            self.fields[name].widget.attrs.update({"class": "form-control"})


class StyledPasswordResetForm(PasswordResetForm):
    """Forgot password request form with styled email input."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update(WIDGETS["email"].attrs)


class StyledSetPasswordForm(SetPasswordForm):
    """Password reset completion form with styled password inputs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("new_password1", "new_password2"):
            self.fields[name].widget.attrs.update(WIDGETS["password"].attrs)
