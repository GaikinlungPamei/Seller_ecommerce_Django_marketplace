"""Authentication, profile and admin user-management views."""
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.views import LoginView
from django.db.models import Count, F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse

from django_App.orders.models import Order, OrderItem
from django_App.products.models import Product, Review

from .decorators import admin_required
from .forms import (CustomerRegisterForm, LoginForm, ProfileForm, ResetPasswordForm, SellerRegisterForm)

User = get_user_model() 


class DjgoLoginView(LoginView): 
    """Login for all three roles — routes each role to its own dashboard."""

    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        user = form.get_user()
        if user.is_blocked:
            messages.error(self.request, "This account has been blocked. Contact support.")
            return self.form_invalid(form)
        response = super().form_valid(form)
        if user.is_admin_role:
            try:
                return redirect("console:dashboard")
            except NoReverseMatch:
                return redirect("accounts:user_list")
        if user.is_seller:
            try:
                return redirect("seller:dashboard")
            except NoReverseMatch:
                return redirect("accounts:profile")
        nxt = self.request.GET.get("next")
        return redirect(nxt) if nxt else response


def register_view(request, role="customer"):
    """Customer / seller registration."""
    if request.user.is_authenticated:
        return redirect("home")

    form_cls = SellerRegisterForm if role == "seller" else CustomerRegisterForm
    form = form_cls()

    if request.method == "POST":
        form = form_cls(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend="django_App.accounts.backends.EmailOrUsernameBackend")
            if user.is_seller:
                messages.success(
                    request,
                    "Seller account created — an administrator must approve it "
                    "before you can publish products.",
                )
                try:
                    return redirect("seller:dashboard")
                except NoReverseMatch:
                    return redirect("accounts:profile")
            messages.success(request, f"Welcome to DJGO, {user.display_name}!") 
            return redirect("home")

    return render(request, "accounts/register.html", {"form": form, "role": role})


def logout_view(request):
    logout(request)
    messages.info(request, "You have been signed out.")
    return redirect("accounts:login")


def profile_view(request):
    """Profile management + password reset."""
    user = request.user
    if not user.is_authenticated:
        return redirect("accounts:login")

    profile_form = ProfileForm(instance=user)
    password_form = ResetPasswordForm(user=user)

    if request.method == "POST":
        if "save_profile" in request.POST:
            profile_form = ProfileForm(request.POST, instance=user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profile updated successfully.")
                return redirect("accounts:profile")
        elif "change_password" in request.POST:
            password_form = ResetPasswordForm(user=user, data=request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                messages.success(request, "Password changed.")
                return redirect("accounts:profile")

    orders = Order.objects.filter(user=user).count() if user.is_customer else 0

    if user.is_admin_role:
        base_layout = "base_admin.html"
    elif user.is_seller:
        base_layout = "base_seller.html"
    else:
        base_layout = "base.html"

    return render(request, "accounts/profile.html", {
        "profile_form": profile_form,
        "password_form": password_form,
        "order_count": orders,
        "base_layout": base_layout,
        "active": "profile",
    })


# --------------------------------------------------------------------------
# Admin: manage customers & sellers
# --------------------------------------------------------------------------
@admin_required
def user_list_view(request):
    role_filter = request.GET.get("role", "")
    status_filter = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()

    users = User.objects.all().annotate(
        order_count=Count("orders", distinct=True),
        product_count=Count("products", distinct=True),
    )

    if role_filter in ("admin", "customer", "seller"):
        users = users.filter(role=role_filter)
    if status_filter in ("active", "pending", "blocked"):
        users = users.filter(status=status_filter)
    if q:
        users = users.filter(
            Q(username__icontains=q) | Q(email__icontains=q) |
            Q(first_name__icontains=q) | Q(last_name__icontains=q) |
            Q(shop_name__icontains=q)
        )
    users = users.order_by("-date_joined")

    return render(request, "accounts/user_list.html", {
        "users": users,
        "role_filter": role_filter,
        "status_filter": status_filter,
        "q": q,
        "total_users": User.objects.count(),
        "admin_count": User.objects.filter(role=User.Role.ADMIN).count(),
        "customer_count": User.objects.filter(role=User.Role.CUSTOMER).count(),
        "seller_count": User.objects.filter(role=User.Role.SELLER).count(),
        "pending_count": User.objects.filter(role=User.Role.SELLER, status=User.Status.PENDING).count(),
        "blocked_count": User.objects.filter(status=User.Status.BLOCKED).count(),
    })


@admin_required
def user_detail_view(request, pk):
    """Admin inspects an individual Customer, Seller, or Admin profile."""
    target = get_object_or_404(User, pk=pk)

    context = {
        "target": target,
        "is_admin": target.role == User.Role.ADMIN or target.is_superuser,
        "is_customer": target.is_customer,
        "is_seller": target.is_seller,
    }

    if target.is_customer:
        customer_orders = list(Order.objects.filter(user=target).prefetch_related("items").order_by("-created_at"))
        spent = (
            Order.objects.filter(user=target, status=Order.Status.DELIVERED)
            .aggregate(s=Sum("total"))["s"] or Decimal("0")
        )
        reviews = list(Review.objects.filter(user=target).select_related("product").order_by("-created_at"))

        context.update({
            "orders": customer_orders,
            "order_count": len(customer_orders),
            "total_spent": spent,
            "reviews": reviews,
            "review_count": len(reviews),
        })
    elif target.is_seller:
        products = list(Product.objects.filter(seller=target).select_related("category").order_by("-created_at"))
        order_items = list(
            OrderItem.objects.filter(seller=target)
            .select_related("order", "product")
            .order_by("-order__created_at")[:25]
        )
        delivered_sales = (
            OrderItem.objects.filter(seller=target, order__status=Order.Status.DELIVERED)
            .annotate(line_sub=F("price") * F("quantity"))
            .aggregate(s=Sum("line_sub"))["s"] or Decimal("0")
        )
        units_sold = (
            OrderItem.objects.filter(seller=target, order__status=Order.Status.DELIVERED)
            .aggregate(u=Sum("quantity"))["u"] or 0
        )

        context.update({
            "products": products,
            "product_count": len(products),
            "order_items": order_items,
            "delivered_sales": delivered_sales,
            "units_sold": units_sold,
            "low_stock_count": sum(1 for p in products if getattr(p, "is_low_stock", False) or getattr(p, "is_out_of_stock", False)),
        })

    return render(request, "accounts/user_detail.html", context)


@admin_required
def set_user_status_view(request, pk, status):
    """Approve / reject sellers, block / unblock any user."""
    target = get_object_or_404(User, pk=pk)
    if status not in dict(User.Status.choices):
        messages.error(request, "Unknown status.")
    elif target == request.user:
        messages.error(request, "You cannot change your own access level.")
    else:
        target.status = status
        target.is_active = status != User.Status.BLOCKED
        target.save(update_fields=["status", "is_active"])
        verb = {"active": "approved / unblocked", "pending": "moved back to pending",
                "blocked": "blocked"}[status]
        messages.success(request, f"{target.display_name} has been {verb}.")
    return redirect(request.META.get("HTTP_REFERER") or reverse("accounts:user_list"))
