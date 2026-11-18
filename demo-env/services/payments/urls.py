from django.urls import path
from payments_app.views import health_check, charge_payment, list_payments

urlpatterns = [
    path("health/", health_check, name="health_check"),
    path("api/payments/charge/", charge_payment, name="charge_payment"),
    path("api/payments/", list_payments, name="list_payments"),
]
