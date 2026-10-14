"""
Storefront home, shopping cart, wishlist, checkout, payment, order tracking,
the seller fulfillment desk and the admin console (incl. coupons + reports).
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.db.models import Avg, Count, F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_POST

from django_App.accounts.decorators import admin_required, customer_required, role_required
from django_App.accounts.models import User
from django_App.products.models import Category, Product, Review

from . import services
from .forms import AddressForm, CouponAdminForm, CouponForm
from .models import (ORDER_STEPS, Address, CartItem, Coupon, Order, OrderItem, WishlistItem)

LINE_REVENUE = F("price") * F("quantity")
SELLER_GROSS = F("sold_items__price") * F("sold_items__quantity")


# --------------------------------------------------------------------------
# Storefront home
# --------------------------------------------------------------------------
class HomeView(View):
    def get(self, request):
        products = (Product.objects.select_related("category", "seller").filter(status=Product.Status.ACTIVE).annotate(avg_rating=Avg("reviews__rating"), review_count=Count("reviews"))[:8])
        categories = (Category.objects.annotate(n=Count("products", filter=Q(products__status=Product.Status.ACTIVE)))[:4])

        wishlist_ids = set()
        if request.user.is_authenticated and request.user.is_customer:
            wishlist_ids = set(request.user.wishlist.values_list("product_id", flat=True))

        stats = {
            "products": Product.objects.filter(status=Product.Status.ACTIVE).count(),
            "sellers": User.objects.filter(role=User.Role.SELLER, status=User.Status.ACTIVE).count(),
            "rating": (Review.objects.aggregate(a=Avg("rating"))["a"] or 0),
        }
        return render(request, "home.html", {
            "products": products, "categories": categories,
            "wishlist_ids": wishlist_ids, "stats": stats,
        })


# --------------------------------------------------------------------------
# Shopping cart
# --------------------------------------------------------------------------
@customer_required
def cart_view(request):
    items = services.cart_lines(request.user)
    subtotal = services.cart_subtotal(request.user)
    shipping = services.shipping_for(subtotal)
    free_gap = max(Decimal(str(settings.FREE_SHIPPING_THRESHOLD)) - subtotal, Decimal("0.00"))

    return render(request, "orders/cart.html", {
        "items": items, "subtotal": subtotal, "shipping": shipping,
        "total": subtotal + shipping, "free_gap": free_gap,
    })


@customer_required
@require_POST
def cart_add(request):
    product = get_object_or_404(Product, pk=request.POST.get("product_id"), status=Product.Status.ACTIVE)
    if product.stock <= 0:
        messages.error(request, f"“{product.title}” is currently out of stock.")
        return redirect(request.POST.get("next") or "orders:cart")

    try:
        qty = max(1, int(request.POST.get("quantity", 1)))
    except (TypeError, ValueError):
        qty = 1
    qty = min(qty, product.stock)

    buy_now = request.POST.get("buy_now") == "1"

    item, created = CartItem.objects.get_or_create(
        user=request.user, product=product, defaults={"quantity": qty})
    if not created:
        new_quantity = min(item.quantity + qty, product.stock)
        if new_quantity == item.quantity:
            messages.info(request, f"You already have all available stock ({product.stock}) for “{product.title}” in your cart.")
            if buy_now:
                return redirect("orders:checkout")
            return redirect(request.POST.get("next") or "orders:cart")
        item.quantity = new_quantity
        item.save(update_fields=["quantity"])

    if buy_now:
        return redirect("orders:checkout")

    messages.success(request, f"Added {qty} × “{product.title}” to your cart.")
    return redirect(request.POST.get("next") or "orders:cart")


@customer_required
@require_POST
def cart_update(request, pk):
    """Manage cart quantity — accepts either an absolute quantity or a +/- delta."""
    item = get_object_or_404(CartItem, pk=pk, user=request.user)
    delta = request.POST.get("delta")
    try:
        if delta is not None:
            new_qty = item.quantity + int(delta)
        else:
            new_qty = int(request.POST.get("quantity", item.quantity))
    except (TypeError, ValueError):
        new_qty = item.quantity

    if new_qty <= 0:
        item.delete()
        messages.info(request, "Item removed from your cart.")
    elif item.product.stock <= 0:
        item.delete()
        messages.warning(request, f"“{item.product.title}” is out of stock and was removed from your cart.")
    else:
        capped = min(new_qty, item.product.stock)
        if capped < new_qty:
            messages.info(request, f"Only {item.product.stock} unit(s) available in stock.")
        item.quantity = capped
        item.save(update_fields=["quantity"])
    return redirect(request.POST.get("next") or "orders:cart")


@customer_required
@require_POST
def cart_remove(request, pk):
    item = get_object_or_404(CartItem, pk=pk, user=request.user)
    title = item.product.title
    item.delete()
    messages.info(request, f"“{title}” removed from your cart.")
    return redirect(request.POST.get("next") or "orders:cart")


# --------------------------------------------------------------------------
# Wishlist
# --------------------------------------------------------------------------
@customer_required
def wishlist_view(request):
    rows = (WishlistItem.objects.filter(user=request.user)
            .select_related("product", "product__category")
            .annotate(avg_rating=Avg("product__reviews__rating"), review_count=Count("product__reviews")))
    return render(request, "orders/wishlist.html", {"items": rows})


@customer_required
@require_POST
def wishlist_toggle(request):
    product = get_object_or_404(Product, pk=request.POST.get("product_id"))
    item = WishlistItem.objects.filter(user=request.user, product=product).first()
    if item:
        item.delete()
        saved = False
        messages.info(request, f"“{product.title}” removed from your wishlist.")
    else:
        WishlistItem.objects.create(user=request.user, product=product)
        saved = True
        messages.success(request, f"“{product.title}” saved to your wishlist.")

    # JSON response for the progressive-enhancement fetch in static/js/main.js
    if request.headers.get("x-requested-with") == "fetch":
        from django.http import JsonResponse

        return JsonResponse({
            "saved": saved,
            "count": WishlistItem.objects.filter(user=request.user).count(),
        })
    return redirect(request.POST.get("next") or "orders:wishlist")


@customer_required
@require_POST
def wishlist_move_to_cart(request, pk):
    item = get_object_or_404(WishlistItem, pk=pk, user=request.user)
    product = item.product
    if not product.is_active:
        messages.error(request, f"“{product.title}” is no longer available.")
    elif not product.is_in_stock:
        messages.error(request, f"“{product.title}” is out of stock.")
    else:
        cart_item, created = CartItem.objects.get_or_create(user=request.user, product=product, defaults={"quantity": 1})
        if not created:
            cart_item.quantity = min(cart_item.quantity + 1, product.stock)
            cart_item.save(update_fields=["quantity"])
        item.delete()
        messages.success(request, f"“{product.title}” moved to your cart.")
    return redirect("orders:wishlist")


# --------------------------------------------------------------------------
# Checkout & payment
# --------------------------------------------------------------------------
@customer_required
def checkout_view(request):
    items = list(services.cart_lines(request.user))
    if not items:
        messages.info(request, "Your cart is empty.")
        return redirect("orders:cart")

    subtotal = services.cart_subtotal(request.user)
    address = services.default_address(request.user)
    address_form = AddressForm(instance=address)

    code = request.session.get("checkout_coupon", "")
    coupon, coupon_message, discount = services.validate_coupon(code, subtotal)
    if code and coupon is None:
        request.session.pop("checkout_coupon", None)
        code, coupon_message = "", coupon_message

    shipping = services.shipping_for(subtotal - discount)
    total = subtotal + shipping - discount
    coupon_form = CouponForm(initial={"code": code} if code else None)

    if request.method == "POST":
        address_form = AddressForm(request.POST)
        if address_form.is_valid():
            addr_data = address_form.cleaned_data
            if request.POST.get("save_address") == "on":
                existing = Address.objects.filter(
                    user=request.user,
                    line1=addr_data["line1"],
                    postal_code=addr_data["postal_code"],
                ).first()
                want_default = request.POST.get("make_default") == "on" or not Address.objects.filter(user=request.user).exists()
                if want_default:
                    Address.objects.filter(user=request.user).update(is_default=False)

                if existing:
                    existing.full_name = addr_data["full_name"]
                    existing.phone = addr_data["phone"]
                    existing.line2 = addr_data.get("line2", "")
                    existing.city = addr_data["city"]
                    existing.state = addr_data["state"]
                    if want_default:
                        existing.is_default = True
                    existing.save()
                else:
                    Address.objects.create(
                        user=request.user,
                        line1=addr_data["line1"],
                        postal_code=addr_data["postal_code"],
                        full_name=addr_data["full_name"],
                        phone=addr_data["phone"],
                        line2=addr_data.get("line2", ""),
                        city=addr_data["city"],
                        state=addr_data["state"],
                        is_default=want_default,
                    )

            order, error = services.place_order(
                request.user,
                {
                    "full_name": addr_data["full_name"], "phone": addr_data["phone"],
                    "line1": addr_data["line1"], "line2": addr_data.get("line2", ""),
                    "city": addr_data["city"], "state": addr_data["state"],
                    "postal_code": addr_data["postal_code"],
                },
                request.POST.get("payment_method", "cod"),
                code,
            )
            if error:
                messages.error(request, error)
            else:
                request.session.pop("checkout_coupon", None)
                if order.payment_method == Order.PaymentMethod.ONLINE:
                    return redirect("orders:razorpay_pay", pk=order.pk)
                return redirect("orders:success", pk=order.pk)
        else:
            messages.error(request, "Please correct the delivery address below.")

    return render(request, "orders/checkout.html", {
        "items": items, "subtotal": subtotal, "shipping": shipping,
        "discount": discount, "total": total, "address_form": address_form,
        "coupon_form": coupon_form, "coupon": coupon, "coupon_code": code,
        "coupon_message": coupon_message,
        "saved_addresses": Address.objects.filter(user=request.user),
        "free_threshold": settings.FREE_SHIPPING_THRESHOLD,
    })


@customer_required
@require_POST
def coupon_apply(request):
    """Apply a coupon code — validated again server-side at order placement."""
    subtotal = services.cart_subtotal(request.user)
    if subtotal <= 0:
        messages.info(request, "Your cart is empty.")
        return redirect("orders:cart")

    form = CouponForm(request.POST)
    if form.is_valid():
        code = form.cleaned_data["code"]
    else:
        code = (request.POST.get("code") or "").strip().upper()

    coupon, message, discount = services.validate_coupon(code, subtotal)

    if coupon:
        request.session["checkout_coupon"] = coupon.code
        messages.success(request, message)
    else:
        request.session.pop("checkout_coupon", None)
        messages.error(request, message or "Enter a valid coupon code.")
    return redirect("orders:checkout")


@customer_required
@require_POST
def coupon_remove(request):
    request.session.pop("checkout_coupon", None)
    messages.info(request, "Coupon removed.")
    return redirect("orders:checkout")


@customer_required
def order_success(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related("items"), pk=pk, user=request.user)
    return render(request, "orders/success.html", {"order": order})


@customer_required
def razorpay_payment_view(request, pk):
    """Razorpay payment gateway checkout screen."""
    order = get_object_or_404(Order, pk=pk, user=request.user)
    if order.status == Order.Status.CANCELLED:
        messages.error(request, "This order has been cancelled.")
        return redirect("orders:detail", pk=order.pk)
    if order.payment_method != Order.PaymentMethod.ONLINE:
        messages.info(request, "This order was placed with Cash on Delivery.")
        return redirect("orders:detail", pk=order.pk)
    if order.payment_status == Order.PaymentStatus.PAID:
        return redirect("orders:success", pk=order.pk)

    key_id = getattr(settings, "RAZORPAY_KEY_ID", "rzp_test_51MockDemoKeyId")
    key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "MockDemoSecretKey123")
    currency = getattr(settings, "RAZORPAY_CURRENCY", "INR")
    amount_paise = int(order.total * 100)

    razorpay_order_id = ""
    is_live_key = False
    try:
        import razorpay
        client = razorpay.Client(auth=(key_id, key_secret))
        rzp_order = client.order.create({
            "amount": amount_paise,
            "currency": currency,
            "payment_capture": "1",
            "notes": {
                "order_ref": order.reference,
                "customer": request.user.username,
            },
        })
        razorpay_order_id = rzp_order["id"]
        is_live_key = True
    except Exception:
        # Fallback for demo/test mode with mock keys
        razorpay_order_id = f"order_mock_{order.reference.replace('-', '_')}"

    return render(request, "orders/razorpay_pay.html", {
        "order": order,
        "key_id": key_id,
        "currency": currency,
        "amount_paise": amount_paise,
        "razorpay_order_id": razorpay_order_id,
        "is_live_key": is_live_key,
        "user_email": request.user.email,
        "user_phone": order.ship_phone,
    })


@customer_required
@require_POST
def razorpay_verify_view(request, pk):
    """Verify Razorpay payment signature and complete the order."""
    order = get_object_or_404(Order, pk=pk, user=request.user)
    if order.status == Order.Status.CANCELLED:
        messages.error(request, "This order has been cancelled.")
        return redirect("orders:my_orders")
    if order.payment_status == Order.PaymentStatus.PAID:
        return redirect("orders:success", pk=order.pk)

    payment_id = request.POST.get("razorpay_payment_id", "").strip()
    razorpay_order_id = request.POST.get("razorpay_order_id", "").strip()
    signature = request.POST.get("razorpay_signature", "").strip()

    if not payment_id:
        messages.error(request, "Payment was not completed. Please try again.")
        return redirect("orders:razorpay_pay", pk=order.pk)

    key_id = getattr(settings, "RAZORPAY_KEY_ID", "rzp_test_51MockDemoKeyId")
    key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "MockDemoSecretKey123")

    verified = False
    if payment_id.startswith("pay_demo_") or payment_id.startswith("pay_mock_") or not signature:
        # Test / demo sandbox verification
        verified = True
    else:
        try:
            import razorpay
            client = razorpay.Client(auth=(key_id, key_secret))
            client.utility.verify_payment_signature({
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            })
            verified = True
        except Exception:
            verified = False

    if verified:
        services.complete_razorpay_payment(order, payment_id, request.user)
        messages.success(request, f"Online payment verified! Transaction Ref: {payment_id}")
        return redirect("orders:success", pk=order.pk)
    else:
        messages.error(request, "Payment signature verification failed. Please try again.")
        return redirect("orders:razorpay_pay", pk=order.pk)


# --------------------------------------------------------------------------
# Customer: order history + tracking + cancellation
# --------------------------------------------------------------------------
@customer_required
def my_orders(request):
    orders = (Order.objects.filter(user=request.user).prefetch_related("items__product", "events").select_related("coupon"))
    reviewed = set(Review.objects.filter(user=request.user).values_list("product_id", flat=True))
    return render(request, "orders/my_orders.html", {
        "orders": orders, "reviewed_ids": reviewed,
        "steps": ORDER_STEPS, "labels": dict(Order.Status.choices),
    })


@customer_required
def order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.prefetch_related("items__product", "events").select_related("coupon"),
        pk=pk, user=request.user)
    reviewed = set(Review.objects.filter(user=request.user).values_list("product_id", flat=True))
    return render(request, "orders/detail.html", {
        "order": order, "reviewed_ids": reviewed,
        "steps": ORDER_STEPS, "labels": dict(Order.Status.choices),
    })


@customer_required
@require_POST
def order_cancel(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    if not order.is_cancellable:
        messages.error(request, "This order can no longer be cancelled.")
    else:
        ok, message = services.cancel_order(order, request.user, "Cancelled by customer")
        (messages.success if ok else messages.error)(request, message)
    return redirect(request.POST.get("next") or "orders:my_orders")


@customer_required
def address_list(request):
    addresses = Address.objects.filter(user=request.user)
    form = AddressForm()
    if request.method == "POST":
        form = AddressForm(request.POST)
        if form.is_valid():
            saved = form.save(commit=False)
            saved.user = request.user
            if request.POST.get("make_default") == "on" or not addresses.exists():
                Address.objects.filter(user=request.user).update(is_default=False)
                saved.is_default = True
            saved.save()
            messages.success(request, "Address saved.")
            return redirect("orders:addresses")
    return render(request, "orders/addresses.html", {"addresses": addresses, "form": form})


@customer_required
@require_POST
def address_delete(request, pk):
    get_object_or_404(Address, pk=pk, user=request.user).delete()
    messages.info(request, "Address deleted.")
    return redirect("orders:addresses")


# --------------------------------------------------------------------------
# Seller: fulfilment desk + sales history
# --------------------------------------------------------------------------
@role_required(User.Role.SELLER)
def seller_dashboard(request):
    user = request.user
    products = Product.objects.filter(seller=user).select_related("category").order_by("-created_at")
    low_stock = [p for p in products if p.is_low_stock or p.is_out_of_stock]
    summary = services.revenue_summary(seller=user)
    chart = services.daily_revenue(days=7, seller=user)

    recent = (
        OrderItem.objects.filter(seller=user)
        .select_related("order", "order__user", "product")
        .order_by("-order__created_at")[:60]
    )
    order_map = {}
    for line in recent:
        entry = order_map.setdefault(line.order_id, {"order": line.order, "lines": [], "total": Decimal("0")})
        entry["lines"].append(line)
        entry["total"] += line.line_total
    recent_orders = list(order_map.values())[:8]

    pending_orders_count = sum(1 for e in order_map.values() if e["order"].status == Order.Status.PENDING)

    return render(request, "seller/dashboard.html", {
        "products": products,
        "recent_products": products[:8],
        "low_stock": low_stock,
        "summary": summary,
        "chart": chart,
        "max_chart": max([c["total"] for c in chart] + [Decimal("1")]),
        "recent_orders": recent_orders,
        "pending_orders_count": pending_orders_count,
        "top_products": (
            OrderItem.objects.filter(seller=user, order__status=Order.Status.DELIVERED)
            .values("title")
            .annotate(units=Sum("quantity"), revenue=Sum(LINE_REVENUE))
            .order_by("-units")[:5]
        ),
        "status_choices": Order.Status.choices,
        "labels": dict(Order.Status.choices),
        "active": "dashboard",
    })


@role_required(User.Role.SELLER)
def seller_orders(request):
    """Customer orders containing this seller's products with search and workflow filters."""
    status_filter = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()

    item_ids = OrderItem.objects.filter(seller=request.user).values_list("order_id", flat=True)
    orders = (Order.objects.filter(pk__in=item_ids).prefetch_related("items", "events").order_by("-created_at"))
    
    if status_filter in dict(Order.Status.choices):
        orders = orders.filter(status=status_filter)

    if q:
        orders = orders.filter(
            Q(reference__icontains=q)
            | Q(ship_name__icontains=q)
            | Q(ship_phone__icontains=q)
            | Q(ship_city__icontains=q)
        )

    lines_by_order = {}
    for line in OrderItem.objects.filter(seller=request.user, order__in=orders).select_related("order"):
        lines_by_order.setdefault(line.order_id, []).append(line)

    groups = []
    for order in orders:
        lines = lines_by_order.get(order.id, [])
        groups.append({
            "order": order,
            "lines": lines,
            "total": sum((l.line_total for l in lines), Decimal("0.00")),
        })

    return render(request, "seller/orders.html", {
        "groups": groups,
        "status_filter": status_filter,
        "q": q,
        "status_choices": Order.Status.choices,
        "labels": dict(Order.Status.choices),
        "active": "orders",
    })


@role_required(User.Role.SELLER)
@require_POST
def seller_order_advance(request, pk):
    """Accept and process a customer order (sellers may only move it forward)."""
    order = get_object_or_404(Order, pk=pk)
    if not OrderItem.objects.filter(order=order, seller=request.user).exists():
        messages.error(request, "That order does not contain your products.")
        return redirect("seller:orders")

    new_status = request.POST.get("status", "")
    if new_status == Order.Status.CANCELLED:
        messages.error(request, "Only an administrator can cancel an order.")
        return redirect("seller:orders")

    ok, message = services.advance_order(order, new_status, request.user)
    (messages.success if ok else messages.error)(request, message)
    return redirect(request.POST.get("next") or "seller:orders")


@role_required(User.Role.SELLER)
def seller_sales(request):
    """Sales history & revenue report for the seller."""
    summary = services.revenue_summary(seller=request.user)
    chart = services.daily_revenue(days=14, seller=request.user)
    items = (OrderItem.objects.filter(seller=request.user).select_related("order", "product").order_by("-order__created_at")[:100])
    return render(request, "seller/sales.html", {
        "summary": summary,
        "chart": chart,
        "items": items,
        "max_chart": max([c["total"] for c in chart] + [Decimal("1")]),
        "active": "sales",
    })


@role_required(User.Role.SELLER)
def seller_reviews(request):
    """Customer ratings and feedback for this seller's products."""
    base_reviews = (
        Review.objects.filter(product__seller=request.user)
        .select_related("product", "user")
        .order_by("-created_at")
    )
    reviews = base_reviews

    q = request.GET.get("q", "").strip()
    if q:
        reviews = reviews.filter(
            Q(product__title__icontains=q)
            | Q(comment__icontains=q)
            | Q(user__first_name__icontains=q)
            | Q(user__last_name__icontains=q)
        )

    rating_filter = request.GET.get("rating", "").strip()
    if rating_filter.isdigit():
        reviews = reviews.filter(rating=int(rating_filter))

    total_count = base_reviews.count()
    avg_agg = base_reviews.aggregate(avg=Avg("rating"))["avg"]
    avg_rating = round(avg_agg or 0, 1)

    breakdown = {}
    for star in range(5, 0, -1):
        count = base_reviews.filter(rating=star).count()
        pct = round((count / total_count * 100)) if total_count else 0
        breakdown[star] = {"count": count, "pct": pct}

    return render(request, "seller/reviews.html", {
        "reviews": reviews,
        "q": q,
        "rating_filter": rating_filter,
        "total_count": total_count,
        "avg_rating": avg_rating,
        "breakdown": breakdown,
        "active": "reviews",
    })


# --------------------------------------------------------------------------
# Admin console: dashboard, orders, coupons, payments
# --------------------------------------------------------------------------
@admin_required
def console_dashboard(request):
    summary = services.revenue_summary()
    chart = services.daily_revenue(days=14)
    counts = User.objects.aggregate(
        customers=Count("id", filter=Q(role=User.Role.CUSTOMER)),
        sellers=Count("id", filter=Q(role=User.Role.SELLER, status=User.Status.ACTIVE)),
        pending=Count("id", filter=Q(role=User.Role.SELLER, status=User.Status.PENDING)),
        blocked=Count("id", filter=Q(status=User.Status.BLOCKED)),
    )
    pending_sellers = (
        User.objects.filter(role=User.Role.SELLER, status=User.Status.PENDING)
        .order_by("-date_joined")[:5]
    )
    recent_customers = (
        User.objects.filter(role=User.Role.CUSTOMER)
        .annotate(order_count=Count("orders"))
        .order_by("-date_joined")[:6]
    )
    sellers_list = (
        User.objects.filter(role=User.Role.SELLER)
        .annotate(product_count=Count("products"))
        .order_by("-date_joined")[:6]
    )
    recent_orders = Order.objects.select_related("user").order_by("-created_at")[:6]
    top_products = (
        OrderItem.objects.exclude(order__status=Order.Status.CANCELLED)
        .values("title")
        .annotate(units=Sum("quantity"), revenue=Sum(LINE_REVENUE))
        .order_by("-units")[:5]
    )
    category_count = Category.objects.count()
    coupon_count = Coupon.objects.count()
    review_count = Review.objects.count()
    product_count = Product.objects.count()
    low_stock = Product.objects.filter(stock__lt=6).count()

    payment_stats = Order.objects.aggregate(
        total_online=Sum("total", filter=Q(payment_method=Order.PaymentMethod.ONLINE)),
        total_cod=Sum("total", filter=Q(payment_method=Order.PaymentMethod.COD)),
        paid_orders=Count("id", filter=Q(payment_status=Order.PaymentStatus.PAID)),
        pending_orders=Count("id", filter=Q(payment_status=Order.PaymentStatus.PENDING)),
    )

    return render(request, "console/dashboard.html", {
        "summary": summary,
        "chart": chart,
        "max_chart": max([c["total"] for c in chart] + [Decimal("1")]),
        "counts": counts,
        "pending_sellers": pending_sellers,
        "recent_customers": recent_customers,
        "sellers_list": sellers_list,
        "recent_orders": recent_orders,
        "top_products": top_products,
        "status_rows": services.status_breakdown(),
        "product_count": product_count,
        "category_count": category_count,
        "coupon_count": coupon_count,
        "review_count": review_count,
        "low_stock": low_stock,
        "payment_stats": payment_stats,
    })


@admin_required
def console_orders(request):
    status_filter = request.GET.get("status", "")
    payment_filter = request.GET.get("payment", "")
    q = request.GET.get("q", "").strip()

    orders = Order.objects.select_related("user", "coupon").prefetch_related("items")
    if status_filter in dict(Order.Status.choices):
        orders = orders.filter(status=status_filter)
    if payment_filter in ("cod", "online"):
        orders = orders.filter(payment_method=payment_filter)
    if q:
        orders = orders.filter(Q(reference__icontains=q) | Q(user__email__icontains=q) | Q(ship_name__icontains=q))

    payments = Order.objects.aggregate(
        online=Sum("total", filter=Q(payment_method="online", payment_status="paid")),
        cod=Sum("total", filter=Q(payment_method="cod", status="delivered", payment_status="paid")),
        cod_due=Sum("total", filter=Q(payment_method="cod", payment_status="pending")),
        refunded=Sum("total", filter=Q(payment_status="refunded")),
        pending=Sum("total", filter=Q(payment_status="pending")),
    )

    return render(request, "console/orders.html", {
        "orders": orders.order_by("-created_at"),
        "status_filter": status_filter, "payment_filter": payment_filter, "q": q,
        "status_choices": Order.Status.choices,
        "payments": {k: (v or Decimal("0.00")) for k, v in payments.items()},
        "labels": dict(Order.Status.choices),
        "total_value": orders.aggregate(t=Sum("total"))["t"] or Decimal("0.00"),
    })


@admin_required
@require_POST
def console_order_advance(request, pk):
    order = get_object_or_404(Order, pk=pk)
    new_status = request.POST.get("status", "")
    if new_status == Order.Status.CANCELLED:
        ok, message = services.cancel_order(order, request.user, "Cancelled by admin")
    else:
        ok, message = services.advance_order(order, new_status, request.user)
    (messages.success if ok else messages.error)(request, message)
    return redirect(request.POST.get("next") or "console:orders")


@admin_required
def console_coupons(request):
    coupons = Coupon.objects.annotate(uses=Count("orders"))
    editing = None
    if request.GET.get("edit"):
        editing = get_object_or_404(Coupon, pk=request.GET["edit"])
    form = CouponAdminForm(instance=editing)

    if request.method == "POST":
        form = CouponAdminForm(request.POST, instance=editing)
        if form.is_valid():
            coupon = form.save()
            messages.success(request, f"Coupon {coupon.code} saved.")
            return redirect("console:coupons")

    return render(request, "console/coupons.html",{"coupons": coupons, "form": form, "editing": editing})


@admin_required
@require_POST
def console_coupon_toggle(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)
    coupon.active = not coupon.active
    coupon.save(update_fields=["active"])
    messages.success(request, f"{coupon.code} is now {'active' if coupon.active else 'inactive'}.")
    return redirect("console:coupons")


@admin_required
@require_POST
def console_coupon_delete(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)
    code = coupon.code
    coupon.delete()
    messages.success(request, f"Coupon {code} deleted.")
    return redirect("console:coupons")


@admin_required
def console_payments(request):
    """Payment monitoring across the marketplace."""
    orders = (Order.objects.select_related("user").prefetch_related("items").order_by("-created_at")[:200])
    totals = Order.objects.aggregate(
        collected=Sum("total", filter=Q(payment_status="paid")),
        pending=Sum("total", filter=Q(payment_status="pending")),
        refunded=Sum("total", filter=Q(payment_status="refunded")),
    )
    return render(request, "console/payments.html", {
        "orders": orders,
        "totals": {k: (v or Decimal("0.00")) for k, v in totals.items()},
    })


@admin_required
def console_reports(request):
    """Sales report — revenue, top products and per-seller performance."""
    summary = services.revenue_summary()
    chart = services.daily_revenue(days=30)

    sellers = (User.objects.filter(role=User.Role.SELLER).annotate(
        product_count=Count("products", distinct=True),
        sold_units=Sum("sold_items__quantity"),
        gross=Sum(SELLER_GROSS),).order_by("-gross"))

    top_products = (OrderItem.objects.exclude(order__status=Order.Status.CANCELLED)
                    .values("title").annotate(units=Sum("quantity"), revenue=Sum(LINE_REVENUE))
                    .order_by("-revenue")[:10])

    return render(request, "console/reports.html", {
        "summary": summary, "chart": chart,
        "max_chart": max([c["total"] for c in chart] + [Decimal("1")]),
        "sellers": sellers, "top_products": top_products,
        "status_rows": services.status_breakdown(),
        "window": f"last {30} days",
        "since": timezone.now() - timedelta(days=30),
    })
