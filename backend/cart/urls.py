from django.urls import path

from cart import views


urlpatterns = [
    path("api/cart", views.cart_detail, name="cart-detail"),
    path("api/cart/actions", views.cart_actions, name="cart-actions"),
    path(
        "api/cart/actions/confirm-text",
        views.cart_action_confirm_text,
        name="cart-action-confirm-text",
    ),
    path(
        "api/cart/actions/<str:action_id>/confirm",
        views.cart_action_confirm,
        name="cart-action-confirm",
    ),
    path("demo/cart/", views.demo_cart, name="demo-cart"),
]
