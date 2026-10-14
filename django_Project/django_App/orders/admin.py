from django.contrib import admin
from .models import Address, Coupon, CartItem, WishlistItem, Order, OrderItem, OrderEvent


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'seller', 'title', 'price', 'quantity', 'line_total')


class OrderEventInline(admin.TabularInline):
    model = OrderEvent
    extra = 0
    readonly_fields = ('status', 'note', 'actor', 'created_at')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('reference', 'user', 'status', 'payment_method', 'payment_status', 'total', 'created_at')
    list_filter = ('status', 'payment_method', 'payment_status', 'created_at')
    search_fields = ('reference', 'user__email', 'ship_name', 'payment_ref')
    inlines = [OrderItemInline, OrderEventInline]
    readonly_fields = ('reference', 'created_at', 'updated_at')


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_percent', 'min_order', 'used_count', 'max_uses', 'active', 'expires_at')
    list_filter = ('active', 'expires_at')
    search_fields = ('code',)


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'full_name', 'phone', 'city', 'state', 'is_default', 'created_at')
    list_filter = ('is_default', 'state', 'created_at')
    search_fields = ('user__email', 'full_name', 'city', 'phone')


admin.site.register(CartItem)
admin.site.register(WishlistItem)
admin.site.register(OrderItem)
admin.site.register(OrderEvent)
