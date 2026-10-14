"""Context processor for cart and wishlist badge counters in the navigation header."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django_App.orders.models import Order, OrderItem
from django_App.products.models import Product

User = get_user_model()


def marketplace_counts(request):
    """Provide real-time cart, wishlist and management counts for authenticated users."""
    cart_count = 0
    wishlist_count = 0
    admin_pending_sellers = 0
    seller_low_stock_count = 0
    seller_pending_orders_count = 0

    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return {
            "cart_count": cart_count,
            "wishlist_count": wishlist_count,
            "admin_pending_sellers": admin_pending_sellers,
            "seller_low_stock_count": seller_low_stock_count,
            "seller_pending_orders_count": seller_pending_orders_count,
        }

    if getattr(user, "is_customer", False) or getattr(user, "is_admin_role", False) or getattr(user, "is_superuser", False):
        cart_count = sum(user.cart.values_list("quantity", flat=True))
        wishlist_count = user.wishlist.count()

    if getattr(user, "is_admin_role", False):
        admin_pending_sellers = User.objects.filter(
            role=User.Role.SELLER, status=User.Status.PENDING
        ).count()

    if getattr(user, "is_seller", False):
        threshold = getattr(settings, "LOW_STOCK_THRESHOLD", 5)
        seller_low_stock_count = Product.objects.filter(seller=user, stock__lt=threshold).count()
        seller_pending_orders_count = OrderItem.objects.filter(
            seller=user, order__status=Order.Status.PENDING
        ).values("order_id").distinct().count()

    return {
        "cart_count": cart_count,
        "wishlist_count": wishlist_count,
        "admin_pending_sellers": admin_pending_sellers,
        "seller_low_stock_count": seller_low_stock_count,
        "seller_pending_orders_count": seller_pending_orders_count,
    }

