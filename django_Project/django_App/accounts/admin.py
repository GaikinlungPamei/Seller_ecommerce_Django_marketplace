from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

User = get_user_model()


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "first_name", "role", "status", "shop_name", "is_active")
    list_filter = ("role", "status", "is_active")
    search_fields = ("username", "email", "first_name", "last_name", "shop_name")
    fieldsets = UserAdmin.fieldsets + (
        ("Marketplace", {"fields": ("role", "status", "shop_name", "phone")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Marketplace", {"fields": ("role", "status", "email", "shop_name")}),
    )
