"""Admin console URLs — mounted at /console/ by the root URLconf."""
from django.urls import path

from . import views

app_name = "console"

urlpatterns = [
    path("", views.console_dashboard, name="dashboard"),
    path("orders/", views.console_orders, name="orders"),
    path("orders/<int:pk>/advance/", views.console_order_advance, name="order_advance"),
    path("coupons/", views.console_coupons, name="coupons"),
    path("coupons/<int:pk>/toggle/", views.console_coupon_toggle, name="coupon_toggle"),
    path("coupons/<int:pk>/delete/", views.console_coupon_delete, name="coupon_delete"),
    path("payments/", views.console_payments, name="payments"),
    path("reports/", views.console_reports, name="reports"),
]
