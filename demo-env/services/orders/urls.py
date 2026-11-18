from django.urls import path
from orders_app.views import health_check, orders_view

urlpatterns = [
    path("health/", health_check, name="health_check"),
    path("api/orders/", orders_view, name="orders_view"),
]
