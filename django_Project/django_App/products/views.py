"""
Storefront catalogue views (browse / search / filter) plus the seller's
product & inventory management screens.
"""
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.contrib import messages
from django.db.models import Avg, Count, Max, Min, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from django_App.accounts.decorators import admin_required, customer_required, seller_required

from django_App.products.form import CategoryForm, ProductForm, QuickStockForm, ReviewForm
from django_App.products.models import Category, Product, Review

SORTS = {
    "new": "-created_at",
    "price-asc": "price",
    "price-desc": "-price",
    "rating": "-avg_rating",
    "title": "title", 
}


def product_list(request):
    """Browse products with search + category / price / rating filters."""
    q = request.GET.get("q", "").strip()
    category_slug = request.GET.get("category", "")
    max_price = request.GET.get("max", "")
    min_rating = request.GET.get("rating", "")
    sort = request.GET.get("sort", "new")
    availability = request.GET.get("availability", "")

    products = (Product.objects.select_related("category", "seller")
                .filter(status=Product.Status.ACTIVE)
                .annotate(avg_rating=Avg("reviews__rating"), review_count=Count("reviews")))

    if q:
        products = products.filter(
            Q(title__icontains=q) | Q(description__icontains=q) |
            Q(category__name__icontains=q) | Q(seller__shop_name__icontains=q)
        )
    category = None
    if category_slug:
        category = get_object_or_404(Category, slug=category_slug)
        products = products.filter(category=category)
    if max_price:
        try:
            products = products.filter(price__lte=Decimal(max_price))
        except (InvalidOperation, TypeError, ValueError):
            pass
    if min_rating:
        try:
            products = products.filter(avg_rating__gte=float(min_rating))
        except (TypeError, ValueError):
            pass
    if availability == "in":
        products = products.filter(stock__gt=0)
    elif availability == "out":
        products = products.filter(stock__lte=0)
    elif availability == "low":
        products = products.filter(stock__gt=0, stock__lt=settings.LOW_STOCK_THRESHOLD)

    products = products.order_by(SORTS.get(sort, "-created_at"))

    price_stats = products.aggregate(min_price=Min("price"), max_price=Max("price"))

    wishlist_ids = set()
    if request.user.is_authenticated and request.user.is_customer:
        wishlist_ids = set(request.user.wishlist.values_list("product_id", flat=True))

    return render(request, "products/list.html", {
        "products": products,
        "categories": Category.objects.annotate(n=Count("products", filter=Q(
            products__status=Product.Status.ACTIVE))),
        "q": q, "category": category, "sort": sort,
        "max_price": max_price, "min_rating": min_rating, "availability": availability,
        "wishlist_ids": wishlist_ids,
        "price_stats": price_stats,
        "total": products.count(),
        "price_options": [{"value": str(v), "label": v} for v in (500, 200, 100)],
        "rating_options": [{"value": "4", "label": "4"}, {"value": "3", "label": "3"}],
        "availability_options": [
            {"value": "in", "label": "In stock"},
            {"value": "low", "label": "Low stock"},
            {"value": "out", "label": "Sold out"},
        ],
    })


def product_detail(request, pk):
    """Product details + reviews + related products."""
    product = get_object_or_404(
        Product.objects.select_related("category", "seller")
        .annotate(avg_rating=Avg("reviews__rating"), review_count=Count("reviews")),
        pk=pk,
    )
    reviews = product.reviews.select_related("user").all()
    related = (Product.objects.filter(category=product.category, status=Product.Status.ACTIVE).exclude(pk=product.pk).annotate(avg_rating=Avg("reviews__rating"), review_count=Count("reviews"))[:4])

    existing_review, can_review = None, False
    if request.user.is_authenticated and request.user.is_customer:
        existing_review = Review.objects.filter(product=product, user=request.user).first()
        can_review = True

    review_form = ReviewForm(instance=existing_review)
    if request.method == "POST" and can_review:
        review_form = ReviewForm(request.POST, instance=existing_review)
        if review_form.is_valid():
            review = review_form.save(commit=False)
            review.product = product
            review.user = request.user
            review.save()
            messages.success(request, "Thanks! Your review has been published.")
            return redirect(product.get_absolute_url())

    wishlist_ids = set()
    if request.user.is_authenticated and (request.user.is_customer or request.user.is_admin_role or request.user.is_superuser):
        wishlist_ids = set(request.user.wishlist.values_list("product_id", flat=True))
    in_wishlist = product.pk in wishlist_ids

    return render(request, "products/detail.html", {
        "product": product, "reviews": reviews, "related": related,
        "review_form": review_form, "can_review": can_review,
        "existing_review": existing_review, "in_wishlist": in_wishlist,
        "wishlist_ids": wishlist_ids,
        "max_qty": max(product.stock, 1),
    })


# --------------------------------------------------------------------------
# Seller: add / edit / delete products, manage price & stock
# --------------------------------------------------------------------------
@seller_required
def seller_product_list(request):
    base_qs = (Product.objects.filter(seller=request.user)
               .select_related("category")
               .annotate(avg_rating=Avg("reviews__rating"), review_count=Count("reviews")))

    threshold = getattr(settings, "LOW_STOCK_THRESHOLD", 5)
    all_low_stock = [p for p in base_qs if p.is_low_stock or p.is_out_of_stock]

    products = base_qs

    # 1. Search products
    q = request.GET.get("q", "").strip()
    if q:
        products = products.filter(
            Q(title__icontains=q) | Q(description__icontains=q) | Q(category__name__icontains=q)
        )

    # 2. Filter by Category
    category_slug = request.GET.get("category", "").strip()
    if category_slug:
        products = products.filter(category__slug=category_slug)

    # 3. Filter by Price
    min_price = request.GET.get("min_price", "").strip()
    max_price = request.GET.get("max_price", "").strip()
    if min_price:
        try:
            products = products.filter(price__gte=Decimal(min_price))
        except (InvalidOperation, TypeError, ValueError):
            pass
    if max_price:
        try:
            products = products.filter(price__lte=Decimal(max_price))
        except (InvalidOperation, TypeError, ValueError):
            pass

    # 4. Filter by Rating
    rating_filter = request.GET.get("rating", "").strip()
    if rating_filter:
        try:
            products = products.filter(avg_rating__gte=float(rating_filter))
        except (TypeError, ValueError):
            pass

    # 5. Stock Management & Product Availability
    stock_status = request.GET.get("stock_status", "").strip()
    if stock_status == "in_stock":
        products = products.filter(stock__gte=threshold)
    elif stock_status == "low_stock":
        products = products.filter(stock__gt=0, stock__lt=threshold)
    elif stock_status == "out_of_stock":
        products = products.filter(stock__lte=0)
    elif stock_status == "active":
        products = products.filter(status=Product.Status.ACTIVE)
    elif stock_status == "inactive":
        products = products.filter(status=Product.Status.INACTIVE)

    # 6. Sorting
    sort = request.GET.get("sort", "-created_at").strip()
    sort_mapping = {
        "-created_at": "-created_at",
        "created_at": "created_at",
        "price_asc": "price",
        "price_desc": "-price",
        "stock_asc": "stock",
        "stock_desc": "-stock",
        "rating_desc": "-avg_rating",
    }
    products = products.order_by(sort_mapping.get(sort, "-created_at"))

    categories = Category.objects.all()
    forms = {p.pk: QuickStockForm(instance=p, prefix=f"p{p.pk}") for p in products}

    return render(request, "products/seller_list.html", {
        "products": products,
        "forms": forms,
        "low_stock": all_low_stock,
        "categories": categories,
        "q": q,
        "category_slug": category_slug,
        "min_price": min_price,
        "max_price": max_price,
        "rating_filter": rating_filter,
        "stock_status": stock_status,
        "sort": sort,
        "total_count": base_qs.count(),
        "active": "products",
    })


@seller_required
def seller_product_create(request):
    form = ProductForm()
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.seller = request.user
            product.save()
            messages.success(request, f"“{product.title}” is now live in the store.")
            return redirect("products:seller_list")
    return render(request, "products/form.html", {
        "form": form,
        "product": None,
        "mode": "Add a product",
        "active": "add_product",
    })


@seller_required
def seller_product_update(request, pk):
    product = get_object_or_404(Product, pk=pk, seller=request.user)
    form = ProductForm(instance=product)
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, f"“{product.title}” updated — price and stock saved.")
            return redirect("products:seller_list")
    return render(request, "products/form.html", {
        "form": form,
        "product": product,
        "mode": f"Edit — {product.title}",
        "active": "products",
    })


@seller_required
@require_POST
def seller_product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk, seller=request.user)
    title = product.title
    product.delete()
    messages.success(request, f"“{title}” deleted.")
    return redirect(request.POST.get("next") or request.META.get("HTTP_REFERER") or "products:seller_list")


@seller_required
@require_POST
def seller_quick_stock_update(request, pk):
    """Update price / stock straight from the inventory table or dashboard."""
    product = get_object_or_404(Product, pk=pk, seller=request.user)
    form = QuickStockForm(request.POST, instance=product, prefix=f"p{pk}")
    if form.is_valid():
        form.save()
        messages.success(request, f"Stock & price updated for “{product.title}”.")
    else:
        messages.error(request, "Could not update stock — check the values.")
    return redirect(request.POST.get("next") or request.META.get("HTTP_REFERER") or "products:seller_list")


@seller_required
def seller_review_list(request):
    return redirect("seller:reviews")


# --------------------------------------------------------------------------
# Admin: catalogue oversight + category management + review moderation
# --------------------------------------------------------------------------
@admin_required
def admin_product_list(request):
    products = (Product.objects.select_related("seller", "category")
                .annotate(avg_rating=Avg("reviews__rating"), review_count=Count("reviews")))
    q = request.GET.get("q", "").strip()
    if q:
        products = products.filter(Q(title__icontains=q) | Q(seller__shop_name__icontains=q))
    return render(request, "console/products.html", {
        "products": products.order_by("-created_at"), "q": q,
        "out_of_stock": products.filter(stock=0).count(),
    })


@admin_required
@require_POST
def admin_product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    title = product.title
    product.delete()
    messages.success(request, f"Listing “{title}” removed from the marketplace.")
    return redirect("products:admin_list")


@admin_required
def admin_category_list(request):
    categories = Category.objects.annotate(n=Count("products"))
    editing = None
    if request.GET.get("edit"):
        editing = get_object_or_404(Category, pk=request.GET["edit"])
    form = CategoryForm(instance=editing)

    if request.method == "POST":
        form = CategoryForm(request.POST, instance=editing)
        if form.is_valid():
            category = form.save()
            messages.success(request, f"Category “{category.name}” saved.")
            return redirect("products:admin_categories")

    return render(request, "console/categories.html", {
        "categories": categories, "form": form, "editing": editing,
    })


@admin_required
@require_POST
def admin_category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    name = category.name
    category.delete()
    messages.success(request, f"Category “{name}” deleted.")
    return redirect("products:admin_categories")


@admin_required
def admin_review_list(request):
    reviews = Review.objects.select_related("user", "product").all()
    return render(request, "console/reviews.html", {"reviews": reviews})


@admin_required
@require_POST
def admin_review_delete(request, pk):
    review = get_object_or_404(Review, pk=pk)
    review.delete()
    messages.success(request, "Review removed.")
    return redirect("products:admin_reviews")


@customer_required
@require_POST
def delete_own_review(request, pk):
    review = get_object_or_404(Review, pk=pk, user=request.user)
    product_pk = review.product_id
    review.delete()
    messages.success(request, "Your review was removed.")
    return redirect("products:detail", pk=product_pk)
