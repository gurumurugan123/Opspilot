from django.urls import path
from inventory_app.views import health_check, check_stock, reserve_stock

urlpatterns = [
    path("health/", health_check, name="health_check"),
    path("api/inventory/<str:item_id>/check/", check_stock, name="check_stock"),
    path("api/inventory/<str:item_id>/reserve/", reserve_stock, name="reserve_stock"),
]
