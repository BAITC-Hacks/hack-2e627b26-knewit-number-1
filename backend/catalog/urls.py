from django.urls import path

from catalog import views


urlpatterns = [
    path("api/products", views.products, name="products"),
    path("api/products/detail", views.product_detail, name="product-detail"),
    path("api/fixtures/product-placeholder.svg", views.fixture_image, name="fixture-image"),
    path("demo/catalog/<int:product_id>/", views.fixture_product_page, name="fixture-product"),
    path("health", views.health, name="health"),
]
