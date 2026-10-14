from django.urls import path

from . import views

app_name = "products"

urlpatterns = [
    # ---- storefront ----
    path("", views.product_list, name="list"),
    path("<int:pk>/", views.product_detail, name="detail"),
    path("review/<int:pk>/delete/", views.delete_own_review, name="delete_review"),

    # ---- seller: product & inventory management ----
    path("seller/products/", views.seller_product_list, name="seller_list"),
    path("seller/products/new/", views.seller_product_create, name="seller_create"),
    path("seller/products/<int:pk>/edit/", views.seller_product_update, name="seller_update"),
    path("seller/products/<int:pk>/delete/", views.seller_product_delete, name="seller_delete"),
    path("seller/products/<int:pk>/stock/", views.seller_quick_stock_update, name="quick_stock"),
    path("seller/reviews/", views.seller_review_list, name="seller_reviews"),

    # ---- admin: catalogue, categories, reviews ----
    path("console/products/", views.admin_product_list, name="admin_list"),
    path("console/products/<int:pk>/delete/", views.admin_product_delete, name="admin_delete"),
    path("console/categories/", views.admin_category_list, name="admin_categories"),
    path("console/categories/<int:pk>/delete/", views.admin_category_delete, name="admin_category_delete"),
    path("console/reviews/", views.admin_review_list, name="admin_reviews"),
    path("console/reviews/<int:pk>/delete/", views.admin_review_delete, name="admin_review_delete"),
]
