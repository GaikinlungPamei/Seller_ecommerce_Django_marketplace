from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    # ---- shopping cart ----
    path("cart/", views.cart_view, name="cart"),
    path("cart/add/", views.cart_add, name="cart_add"),
    path("cart/<int:pk>/update/", views.cart_update, name="cart_update"),
    path("cart/<int:pk>/remove/", views.cart_remove, name="cart_remove"),

    # ---- wishlist ----
    path("wishlist/", views.wishlist_view, name="wishlist"),
    path("wishlist/toggle/", views.wishlist_toggle, name="wishlist_toggle"),
    path("wishlist/<int:pk>/move/", views.wishlist_move_to_cart, name="wishlist_move"),

    # ---- checkout, coupons & payment ----
    path("checkout/", views.checkout_view, name="checkout"),
    path("checkout/pay/<int:pk>/", views.razorpay_payment_view, name="razorpay_pay"),
    path("checkout/verify/<int:pk>/", views.razorpay_verify_view, name="razorpay_verify"),
    path("checkout/coupon/apply/", views.coupon_apply, name="coupon_apply"),
    path("checkout/coupon/remove/", views.coupon_remove, name="coupon_remove"),
    path("checkout/success/<int:pk>/", views.order_success, name="success"),

    # ---- customer order history & tracking ----
    path("my-orders/", views.my_orders, name="my_orders"),
    path("my-orders/<int:pk>/", views.order_detail, name="detail"),
    path("my-orders/<int:pk>/cancel/", views.order_cancel, name="cancel"),
    path("addresses/", views.address_list, name="addresses"),
    path("addresses/<int:pk>/delete/", views.address_delete, name="address_delete"),
]
