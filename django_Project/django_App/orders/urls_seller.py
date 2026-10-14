"""Seller studio URLs — mounted at /seller/ by the root URLconf."""
from django.urls import path

from . import views

app_name = "seller"

urlpatterns = [
    path("", views.seller_dashboard, name="dashboard"),
    path("orders/", views.seller_orders, name="orders"),
    path("orders/<int:pk>/advance/", views.seller_order_advance, name="order_advance"),
    path("sales/", views.seller_sales, name="sales"),
    path("reviews/", views.seller_reviews, name="reviews"),
]
