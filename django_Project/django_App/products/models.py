"""
Module 2 — Product and Inventory Management.

Categories, products (with image upload), stock levels and reviews/ratings.
"""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

SAMPLE_IMAGES = [
    "images/headphones.jpg", "images/watch.jpg", "images/sneakers.jpg",
    "images/backpack.jpg", "images/sunglasses.jpg", "images/camera.jpg",
    "images/keyboard.jpg", "images/lamp.jpg", "images/bottle.jpg",
    "images/jackets.jpg",
]


class Category(models.Model):
    """Category management (admin only)."""

    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return f"{reverse('products:list')}?category={self.slug}"


class Product(models.Model):
    """A seller's listing."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="products")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    stock = models.PositiveIntegerField(default=0, help_text="Units in stock")
    image = models.ImageField(upload_to="products/", blank=True, null=True, help_text="Product image upload")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["title"]), models.Index(fields=["status"])]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title) or "product"
            slug, n = base, 1
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                n += 1
                slug = f"{base}-{n}"
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("products:detail", args=[self.pk])

    # ---- inventory helpers --------------------------------------------
    @property
    def is_in_stock(self):
        return self.stock > 0

    @property
    def is_low_stock(self):
        return 0 < self.stock < settings.LOW_STOCK_THRESHOLD

    @property
    def is_out_of_stock(self):
        return self.stock <= 0

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    # ---- rating helpers ------------------------------------------------
    @property
    def average_rating(self):
        """(value, count) — used when a queryset has not pre-annotated the averages."""
        agg = self.reviews.aggregate(avg=models.Avg("rating"), n=models.Count("id"))
        return round(agg["avg"] or 0, 1), agg["n"] or 0

    @property
    def rating_value(self):
        return self.average_rating[0]

    @property
    def review_total(self):
        return self.average_rating[1]

    @property
    def display_image(self):
        """Uploaded image, else a bundled sample so the storefront never breaks."""
        if self.image:
            return self.image.url
        idx = (self.pk or 0) % len(SAMPLE_IMAGES)
        return f"{settings.STATIC_URL}{SAMPLE_IMAGES[idx]}"


class Review(models.Model):
    """Product reviews and ratings (one per customer per product)."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("product", "user")

    def __str__(self):
        return f"{self.rating}★ on {self.product.title}"
