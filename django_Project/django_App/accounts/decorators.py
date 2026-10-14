"""Role-based access decorators (Role-Based Authentication)."""
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def login_redirect(request):
    """Send anonymous users to the login page, remembering where they came from."""
    next_url = request.POST.get("next") or request.GET.get("next") or request.get_full_path()
    return redirect(f"/accounts/login/?next={next_url}")


def _deny(request, reason):
    messages.error(request, reason)
    return redirect("home")


def _guard(request, predicate, denial_message):
    """Shared pre-flight: authenticated, not blocked, and allowed by predicate."""
    user = request.user
    if not user.is_authenticated:
        return login_redirect(request)
    if getattr(user, "is_blocked", False):
        return _deny(request, "Your account has been blocked. Contact support.")
    if not predicate(user):
        return _deny(request, denial_message)
    return None


def role_required(*roles):
    """Allow only the given roles."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            blocked = _guard(
                request,
                lambda u: u.role in roles or u.is_superuser,
                "You do not have access to that area.",
            )
            return blocked or view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def customer_required(view_func):
    """Customer-only area (cart, wishlist, checkout, order history)."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        blocked = _guard(request, lambda u: u.is_customer or u.is_admin_role or u.is_superuser, "This area is for customers only.")
        return blocked or view_func(request, *args, **kwargs)

    return _wrapped


def seller_required(view_func):
    """Approved-seller area (product & inventory management)."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        blocked = _guard(request, lambda u: u.is_seller, "This area is for sellers only.")
        if blocked:
            return blocked
        if not user.is_approved_seller:
            messages.warning(
                request,
                "Your seller account is awaiting admin approval — product "
                "publishing unlocks once you are approved.",
            )
            return redirect("seller:dashboard")
        return view_func(request, *args, **kwargs)

    return _wrapped


def admin_required(view_func):
    """Admin-only area (the /console/ dashboard)."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        blocked = _guard(request, lambda u: u.is_admin_role, "Administrator access required.")
        return blocked or view_func(request, *args, **kwargs)

    return _wrapped
