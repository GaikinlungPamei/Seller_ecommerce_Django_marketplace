"""
Module 1 — User and Authentication Management.

Custom user model supporting the three roles of the system:
admin, seller and customer, with a moderation status used for seller
approval and for blocking/unblocking users.
"""
from django.contrib.auth.models import AbstractUser, UserManager as DefaultUserManager
from django.db import models


class UserManager(DefaultUserManager):
    """Custom manager ensuring superusers are automatically assigned the ADMIN role."""

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("status", User.Status.ACTIVE)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """Custom user model (Django Custom User Model requirement)."""

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        SELLER = "seller", "Seller"
        CUSTOMER = "customer", "Customer"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PENDING = "pending", "Pending approval"
        BLOCKED = "blocked", "Blocked"

    objects = UserManager()

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CUSTOMER)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    shop_name = models.CharField(max_length=120, blank=True, null=True, help_text="Seller storefront name")
    phone = models.CharField(max_length=30, blank=True, null=True)

    REQUIRED_FIELDS = ["email"]

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.role})"

    def save(self, *args, **kwargs):
        if self.is_superuser and self.role != self.Role.ADMIN:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    # ---- role helpers -------------------------------------------------
    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_seller(self):
        return self.role == self.Role.SELLER

    @property
    def is_customer(self):
        return self.role == self.Role.CUSTOMER

    @property
    def is_approved_seller(self):
        return self.is_seller and self.status == self.Status.ACTIVE

    @property
    def is_blocked(self):
        return self.status == self.Status.BLOCKED

    @property
    def display_name(self):
        return self.get_full_name() or self.email or self.username
