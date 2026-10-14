"""
Order & payment service layer.

Centralize the checkout maths, stock movement, order-status workflow and
email notifications so views stay thin.
"""
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from django.core.mail import send_mail
from django.db import models, transaction
from django.utils import timezone

from django_App.products.models import Product

from .models import ORDER_STEPS, Address, CartItem, Coupon, Order, OrderEvent, OrderItem

STATUS_LABELS = dict(Order.Status.choices)


def shipping_for(subtotal: Decimal) -> Decimal:
    """Free shipping above the threshold, flat fee otherwise."""
    if subtotal <= 0 or subtotal >= Decimal(str(settings.FREE_SHIPPING_THRESHOLD)):
        return Decimal("0.00")
    return Decimal(str(settings.FLAT_SHIPPING_FEE))


def cart_lines(user):
    return (CartItem.objects.filter(user=user)
            .select_related("product", "product__seller", "product__category")
            .order_by("-created_at"))


def cart_subtotal(user) -> Decimal:
    return sum((i.line_total for i in cart_lines(user)), Decimal("0.00"))


def validate_coupon(code: str, subtotal: Decimal) -> Tuple[Optional[Coupon], str, Decimal]:
    """Return (coupon|None, message, discount)."""
    code = (code or "").strip().upper()
    if not code:
        return None, "", Decimal("0.00")
    try:
        coupon = Coupon.objects.get(code=code)
    except Coupon.DoesNotExist:
        return None, "That coupon code does not exist.", Decimal("0.00")
    ok, message = coupon.validate_for(subtotal)
    if not ok:
        return None, message, Decimal("0.00")
    return coupon, message, coupon.discount_for(subtotal)


def default_address(user) -> Optional[Address]:
    address = Address.objects.filter(user=user, is_default=True).first()
    return address or Address.objects.filter(user=user).first()


@transaction.atomic
def place_order(user, address_data: Dict[str, Any], payment_method: str, coupon_code: str) -> Tuple[Optional[Order], Optional[str]]:
    """
    Checkout: validate stock, apply the coupon, snapshot the address,
    create the order + items, decrement stock and clear the cart.

    Returns (order, error_message).
    """
    lines = list(cart_lines(user))
    if not lines:
        return None, "Your cart is empty."

    for item in lines:
        try:
            product = Product.objects.select_for_update().get(pk=item.product_id)
        except Product.DoesNotExist:
            return None, "A product in your cart is no longer available."
        if not product.is_active:
            return None, f"“{product.title}” is no longer available."
        if product.stock < item.quantity:
            return None, (f"Only {product.stock} left in stock for “{product.title}” "f"({item.quantity} requested).")

    subtotal = cart_subtotal(user)
    coupon, coupon_message, discount = validate_coupon(coupon_code, subtotal)
    if coupon_code and coupon is None:
        return None, coupon_message

    shipping = shipping_for(subtotal - discount)
    total = (subtotal + shipping - discount).quantize(Decimal("0.01"))

    method = (payment_method or "cod").lower()
    if method not in dict(Order.PaymentMethod.choices):
        method = Order.PaymentMethod.COD

    order = Order.objects.create(
        user=user,
        status=Order.Status.PENDING,
        payment_method=method,
        payment_status=Order.PaymentStatus.PENDING,
        subtotal=subtotal, shipping=shipping, discount=discount, total=total,
        coupon=coupon,
        ship_name=address_data["full_name"],
        ship_phone=address_data["phone"],
        ship_line1=address_data["line1"],
        ship_line2=address_data.get("line2", ""),
        ship_city=address_data["city"],
        ship_state=address_data["state"],
        ship_postal=address_data.get("postal_code") or address_data.get("ship_postal", ""),
    )

    for item in lines:
        product = item.product
        OrderItem.objects.create(
            order=order, product=product, seller=product.seller,
            title=product.title, image=product.display_image,
            price=product.price, quantity=item.quantity,
        )
        Product.objects.filter(pk=product.pk).update(stock=models.F("stock") - item.quantity)

    if coupon:
        Coupon.objects.filter(pk=coupon.pk).update(used_count=coupon.used_count + 1)

    CartItem.objects.filter(user=user).delete()
    log_event(order, Order.Status.PENDING, "Order placed", user)

    # If cash on delivery, send confirmation immediately
    if method == Order.PaymentMethod.COD:
        send_order_email(order)

    check_and_send_low_stock_alerts(order)
    return order, None


def complete_razorpay_payment(order, payment_id, user=None):
    """Mark order as paid via Razorpay and send order confirmation notification."""
    order.payment_status = Order.PaymentStatus.PAID
    order.payment_ref = payment_id
    order.save(update_fields=["payment_status", "payment_ref"])
    log_event(order, order.status, f"Online payment verified via Razorpay (Ref: {payment_id})", user)
    send_order_email(order)


def simulate_online_payment(order):
    """Fallback payment reference generator."""
    return f"pay_{uuid.uuid4().hex[:16]}"


def log_event(order, status, note="", actor=None):
    OrderEvent.objects.create(order=order, status=status, note=note, actor=actor)


@transaction.atomic
def advance_order(order: Order, new_status: str, actor=None, note: str = "") -> Tuple[bool, str]:
    """Move an order forward through its fulfillment workflow (admin or seller)."""
    if new_status not in dict(Order.Status.choices):
        return False, "Unknown status."
    if not order.is_open:
        return False, "This order is already closed."

    if new_status == Order.Status.CANCELLED:
        return cancel_order(order, actor, note or "Cancelled by staff")

    if new_status not in ORDER_STEPS:
        return False, "Unknown fulfillment step."
    current = ORDER_STEPS.index(order.status) if order.status in ORDER_STEPS else -1
    nxt = ORDER_STEPS.index(new_status)
    if nxt <= current:
        return False, "Orders can only move forward through the workflow."

    order.status = new_status
    if new_status == Order.Status.DELIVERED and order.payment_method == Order.PaymentMethod.COD:
        order.payment_status = Order.PaymentStatus.PAID  # cash collected on delivery
    order.save()
    log_event(order, new_status, note or f"Marked {STATUS_LABELS[new_status].lower()}", actor)
    send_status_email(order)
    return True, f"Order {order.reference} marked {STATUS_LABELS[new_status].lower()}."


@transaction.atomic
def cancel_order(order: Order, actor=None, note: str = "") -> Tuple[bool, str]:
    """Cancel an order, restock the items and refund online payments."""
    if not order.is_open:
        return False, "Only pending or in-progress orders can be cancelled."

    for item in order.items.select_for_update():
        Product.objects.filter(pk=item.product_id).update(stock=models.F("stock") + item.quantity)

    if order.coupon:
        Coupon.objects.filter(pk=order.coupon_id, used_count__gt=0).update(used_count=models.F("used_count") - 1)

    refunded = order.payment_status == Order.PaymentStatus.PAID
    order.status = Order.Status.CANCELLED
    if refunded:
        order.payment_status = Order.PaymentStatus.REFUNDED
    order.save()
    log_event(order, Order.Status.CANCELLED, note or "Cancelled — stock restored", actor)
    send_status_email(order, refunded=refunded)
    return True, (f"Order {order.reference} cancelled." + (" Payment refunded." if refunded else ""))


def _money(value):
    return f"${Decimal(value).quantize(Decimal('0.01'))}"


def send_order_email(order):
    """Order confirmation email notification."""
    lines = "\n".join(f"  • {i.title} × {i.quantity} — {_money(i.line_total)}" 
    for i in order.items.all())
    first_name = (order.ship_name or "Customer").split(" ")[0]
    body = (
        f"Hi {first_name},\n\n"
        f"Thanks for your order {order.reference}.\n\n"
        f"{lines}\n\n"
        f"Subtotal: {_money(order.subtotal)}\n"
        f"Shipping: {_money(order.shipping)}\n"
        + (f"Discount ({order.coupon.code}): -{_money(order.discount)}\n" if order.coupon else "")
        + f"Total: {_money(order.total)}\n"
        f"Payment: {order.get_payment_method_display()} ({order.get_payment_status_display()})\n\n"
        f"Shipping to:\n{order.ship_one_line}\n\n"
        f"Track your order any time from your account page.\n— DJGO Marketplace"
    )
    _send("Your DJGO order is confirmed", body, order)


def send_status_email(order, refunded=False):
    """Order status / tracking update notification."""
    first_name = (order.ship_name or "Customer").split(" ")[0]
    subject = f"Order {order.reference}: {STATUS_LABELS.get(order.status, order.status)}"
    body = (
        f"Hi {first_name},\n\n"
        f"Your order {order.reference} is now {STATUS_LABELS.get(order.status, order.status).lower()}.\n"
        + ("\nAny online payment has been refunded to the original method.\n" if refunded else "")
        + f"\nTotal: {_money(order.total)}\n— DJGO Marketplace"
    )
    _send(subject, body, order)


def _send(subject, body, order):
    if not order.user.email:
        return
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [order.user.email], fail_silently=True)
    except Exception:  # pragma: no cover — never break checkout on email issues
        pass


def check_and_send_low_stock_alerts(order):
    """Notify sellers whenever product stock reaches or falls below LOW_STOCK_THRESHOLD."""
    threshold = getattr(settings, "LOW_STOCK_THRESHOLD", 5)
    for item in order.items.select_related("product", "seller"):
        # Refresh current stock from db
        remaining = Product.objects.filter(pk=item.product_id).values_list("stock", flat=True).first()
        if remaining is not None and remaining <= threshold:
            send_low_stock_email(item.product, remaining)


def send_low_stock_email(product, remaining):
    """Dispatch low stock / out of stock warning to the seller's registered email."""
    seller = product.seller
    if not seller or not getattr(seller, "email", None):
        return
    status_label = "OUT OF STOCK" if remaining <= 0 else "LOW STOCK"
    subject = f"[{status_label} ALERT] “{product.title}” has {remaining} unit(s) remaining"
    body = (
        f"Hi {seller.display_name},\n\n"
        f"This is an automated inventory alert from the marketplace.\n\n"
        f"Product: {product.title}\n"
        f"Remaining Stock: {remaining} unit(s)\n"
        f"Status: {status_label}\n\n"
        f"Customer demand has reduced your available stock below your threshold of {settings.LOW_STOCK_THRESHOLD} units.\n"
        f"Please update your inventory or restock this item from your Seller Studio:\n"
        f"/products/seller/products/\n\n"
        f"— DJGO Marketplace Automated Inventory System"
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [seller.email], fail_silently=True)
    except Exception:
        pass


def _money_field():
    from django.db.models import DecimalField

    return DecimalField(max_digits=12, decimal_places=2)


def revenue_summary(seller=None):
    """Sales report + revenue dashboard aggregates (admin: all, seller: own)."""
    from django.db.models import F, Sum, Value
    from django.db.models.functions import Coalesce

    field = _money_field()
    items = OrderItem.objects.select_related("order", "product")
    orders = Order.objects.all()
    if seller is not None:
        items = items.filter(seller=seller)
        orders = orders.filter(items__seller=seller).distinct()

    live = orders.exclude(status=Order.Status.CANCELLED)

    delivered_items = items.filter(order__status=Order.Status.DELIVERED)
    line_total = F("price") * F("quantity")
    revenue = delivered_items.aggregate(
        total=Coalesce(Sum(line_total, output_field=field), Value(0), output_field=field)
    )["total"] or Decimal("0.00")

    pipeline = live.exclude(status=Order.Status.DELIVERED).aggregate(
        total=Coalesce(Sum("total"), Value(0), output_field=field)
    )["total"] or Decimal("0.00")

    return {
        "orders": live.count(),
        "delivered_orders": live.filter(status=Order.Status.DELIVERED).count(),
        "cancelled_orders": orders.filter(status=Order.Status.CANCELLED).count(),
        "open_orders": live.exclude(status=Order.Status.DELIVERED).count(),
        "units": items.filter(order__in=live).aggregate(n=Coalesce(Sum("quantity"), Value(0)))["n"],
        "revenue": revenue,
        "pipeline_value": pipeline,
    }


def daily_revenue(days=7, seller=None):
    """Revenue grouped per day for the dashboard charts."""
    from datetime import timedelta

    from django.db.models import DecimalField, Sum
    from django.db.models.functions import TruncDay

    since = timezone.now() - timedelta(days=days - 1)
    qs = (Order.objects.filter(created_at__date__gte=since.date()).exclude(status=Order.Status.CANCELLED))
    if seller is not None:
        qs = qs.filter(items__seller=seller).distinct()

    rows = (qs.annotate(day=TruncDay("created_at"))
            .values("day")
            .annotate(total=Sum("total", output_field=DecimalField(max_digits=12, decimal_places=2)))
            .order_by("day"))
    by_day = {r["day"].date(): r["total"] or Decimal("0.00") for r in rows}

    out = []
    for i in range(days):
        day = (since + timedelta(days=i)).date()
        out.append({"date": day, "label": day.strftime("%a"),
                    "total": by_day.get(day, Decimal("0.00"))})
    return out


def status_breakdown(seller=None):
    """Order counts per status, for the stacked report bar."""
    from django.db.models import Count

    qs = Order.objects.all()
    if seller is not None:
        qs = qs.filter(items__seller=seller).distinct()
    rows = qs.values("status").annotate(n=Count("id")).order_by("status")
    counts = {r["status"]: r["n"] for r in rows}
    total = sum(counts.values()) or 1
    return [{"status": s, "label": STATUS_LABELS.get(s, s), "n": counts.get(s, 0),
             "pct": round(counts.get(s, 0) * 100 / total)} for s in dict(Order.Status.choices)]
