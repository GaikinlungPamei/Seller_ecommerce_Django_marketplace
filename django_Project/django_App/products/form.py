"""Product, category and review forms."""
from django import forms

from django_App.products.models import Category, Product, Review


class ProductForm(forms.ModelForm):
    """Add / edit a product, including its image, price and stock."""

    class Meta:
        model = Product
        fields = ("title", "description", "category", "price", "stock", "image", "status")
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Aria Wireless Headphones"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Describe the product, materials, warranty…"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
            "stock": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }


class QuickStockForm(forms.ModelForm):
    """Inline price / stock update from the inventory table."""

    class Meta:
        model = Product
        fields = ("price", "stock")
        widgets = {
            "price": forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0.01"}),
            "stock": forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": "0"}),
        }


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ("name", "description")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Tech & Audio"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class ReviewForm(forms.ModelForm):
    """Rate and review a product."""

    class Meta:
        model = Review
        fields = ("rating", "comment")
        widgets = {
            "comment": forms.Textarea(attrs={
                "class": "form-control", "rows": 3,
                "placeholder": "What did you think? Fit, quality, shipping…"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rating"].widget = forms.Select(
            attrs={"class": "form-select"},
            choices=[(i, f"{i} star{'s' if i > 1 else ''}") for i in range(5, 0, -1)],
        )
        self.fields["rating"].initial = 5
