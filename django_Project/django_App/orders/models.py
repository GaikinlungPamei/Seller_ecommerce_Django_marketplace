"""
Module 3 — Order and Payment Management.

Covers the shopping cart, wishlist, coupon system, delivery addresses,
orders / order items, payment method & status, and order-status tracking.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

ORDER_STEPS = ["pending", "confirmed", "shipped", "out_for_delivery", "delivered"]


class Address(models.Model):
    """Delivery address book for customers."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30)
    line1 = models.CharField(max_length=200)
    line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    postal_code = models.CharField(max_length=20)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "addresses"

    def __str__(self):
        return f"{self.full_name} — {self.city}"

    @property
    def one_line(self):
        parts = [self.line1, self.line2, self.city, self.state, self.postal_code]
        return ", ".join([p for p in parts if p])


class Coupon(models.Model):
    """Coupon and discount system (admin managed)."""

    code = models.CharField(max_length=40, unique=True)
    discount_percent = models.PositiveSmallIntegerField()
    min_order = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    max_uses = models.PositiveIntegerField(default=1000)
    used_count = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} ({self.discount_percent}%)"

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return bool(self.expires_at and self.expires_at < timezone.now())

    @property
    def is_redeemed_out(self):
        return self.used_count >= self.max_uses

    @property
    def is_valid(self):
        return self.active and not self.is_expired and not self.is_redeemed_out

    def validate_for(self, subtotal):
        """Return (ok: bool, message: str)."""
        if not self.is_valid:
            return False, "That coupon is inactive or expired."
        if self.is_redeemed_out:
            return False, "That coupon has been fully redeemed."
        if subtotal < self.min_order:
            return False, f"This coupon requires a minimum order of ${self.min_order}."
        return True, f"{self.code} applied — {self.discount_percent}% off."

    def discount_for(self, subtotal):
        return (subtotal * Decimal(self.discount_percent) / Decimal(100)).quantize(Decimal("0.01"))


class CartItem(models.Model):
    """Shopping cart line."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,related_name="cart")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE)
    quantity = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("user", "product")

    def __str__(self):
        return f"{self.quantity} × {self.product.title}"

    @property
    def line_total(self):
        return (self.product.price * self.quantity).quantize(Decimal("0.01"))


class WishlistItem(models.Model):
    """Wishlist entry."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("user", "product")

    def __str__(self):
        return f"{self.user.display_name} ♥ {self.product.title}"


class Order(models.Model):
    """A placed order with a payment + fulfillment lifecycle."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        SHIPPED = "shipped", "Shipped"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentMethod(models.TextChoices):
        COD = "cod", "Cash on delivery"
        ONLINE = "online", "Online payment"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        REFUNDED = "refunded", "Refunded"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders")
    reference = models.CharField(max_length=20, unique=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices, default=PaymentMethod.COD)
    payment_status = models.CharField(max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    payment_ref = models.CharField(max_length=80, blank=True, null=True, help_text="Gateway reference for online payments")

    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    shipping = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=10, decimal_places=2)
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")

    # shipping address snapshot (immutable once the order is placed)
    ship_name = models.CharField(max_length=120)
    ship_phone = models.CharField(max_length=30)
    ship_line1 = models.CharField(max_length=200)
    ship_line2 = models.CharField(max_length=200, blank=True)
    ship_city = models.CharField(max_length=80)
    ship_state = models.CharField(max_length=80)
    ship_postal = models.CharField(max_length=20)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)
        if creating and not self.reference:
            # stamp a human-friendly reference once we know the primary key
            self.reference = f"VR-{self.created_at.strftime('%y%m%d')}-{self.pk:05d}"
            super().save(update_fields=["reference"])

    def __str__(self):
        return self.reference

    # ---- helpers -------------------------------------------------------
    @property
    def item_count(self):
        return sum(i.quantity for i in self.items.all())

    @property
    def seller_revenue(self):
        """Per-seller revenue map used by the seller sales history."""
        out = {}
        for i in self.items.select_related("product__seller"):
            seller = i.product.seller
            out[seller] = out.get(seller, Decimal("0")) + i.line_total
        return out

    @property
    def progress_index(self):
        if self.status == self.Status.CANCELLED:
            return -1
        values = [c[0] for c in self.Status.choices if c[0] in ORDER_STEPS]
        return values.index(self.status) if self.status in values else 0

    @property
    def next_status(self):
        idx = self.progress_index
        if idx < 0 or idx >= len(ORDER_STEPS) - 1:
            return None
        return ORDER_STEPS[idx + 1]

    @property
    def is_open(self):
        return self.status not in (self.Status.DELIVERED, self.Status.CANCELLED)

    @property
    def is_cancellable(self):
        return self.status in (self.Status.PENDING, self.Status.CONFIRMED)

    @property
    def ship_one_line(self):
        parts = [self.ship_line1, self.ship_line2, self.ship_city, f"{self.ship_state} {self.ship_postal}"]
        return ", ".join([p for p in parts if p])

    @property
    def ship_address(self):
        return self.ship_one_line



class OrderItem(models.Model):
    """Order line — snapshots title, image and price at purchase time."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT)
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sold_items")
    title = models.CharField(max_length=160)
    image = models.CharField(max_length=300, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveSmallIntegerField()

    def __str__(self):
        return f"{self.quantity} × {self.title}"

    @property
    def line_total(self):
        return (self.price * self.quantity).quantize(Decimal("0.01"))


class OrderEvent(models.Model):
    """Order tracking timeline entries."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=20)
    note = models.CharField(max_length=200, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.order.reference} → {self.status}"
