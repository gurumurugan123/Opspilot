import os
import logging
import requests
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import Order

logger = logging.getLogger(__name__)

@api_view(["GET"])
def health_check(request):
    """Liveness & Readiness probe for orders-service."""
    if os.getenv("FAIL_READINESS_PROBE", "false").lower() == "true":
        logger.error("Orders service readiness probe failed artificially.")
        return Response({"status": "unhealthy"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response({"status": "healthy", "service": "orders-service"})

@api_view(["POST", "GET"])
def orders_view(request):
    """
    POST: Create an order, verify inventory, and charge payment.
    GET: List recent orders.
    """
    if request.method == "GET":
        orders = Order.objects.all().order_by("-created_at")[:50]
        data = [
            {"id": str(o.id), "item_id": o.item_id, "quantity": o.quantity, "total_amount": str(o.total_amount), "status": o.status}
            for o in orders
        ]
        return Response(data)

    # Process POST (Create order)
    item_id = request.data.get("item_id", "item_101")
    quantity = int(request.data.get("quantity", 1))
    total_amount = request.data.get("total_amount", "99.00")

    order = Order.objects.create(
        item_id=item_id,
        quantity=quantity,
        total_amount=total_amount,
        status="CREATED"
    )

    # Step 1: Check inventory
    inventory_url = f"{settings.INVENTORY_SERVICE_URL}/api/inventory/{item_id}/check/"
    try:
        inv_res = requests.get(inventory_url, timeout=settings.DOWNSTREAM_TIMEOUT)
        if inv_res.status_code != 200:
            order.status = "FAILED"
            order.error_message = f"Inventory service returned HTTP {inv_res.status_code}"
            order.save()
            logger.error(f"Failed inventory check for {item_id}: HTTP {inv_res.status_code}")
            return Response({"error": order.error_message}, status=status.HTTP_502_BAD_GATEWAY)
        
        inv_data = inv_res.json()
        if not inv_data.get("in_stock"):
            order.status = "FAILED"
            order.error_message = f"Item {item_id} is out of stock"
            order.save()
            return Response({"error": order.error_message}, status=status.HTTP_400_BAD_REQUEST)
    except requests.exceptions.RequestException as e:
        order.status = "FAILED"
        order.error_message = f"Downstream inventory error: {str(e)}"
        order.save()
        logger.error(f"Downstream dependency timeout or connection error to Inventory: {str(e)}")
        return Response({"error": order.error_message}, status=status.HTTP_504_GATEWAY_TIMEOUT)

    # Step 2: Charge Payment
    payment_url = f"{settings.PAYMENTS_SERVICE_URL}/api/payments/charge/"
    try:
        pay_res = requests.post(payment_url, json={"order_id": str(order.id), "amount": str(total_amount)}, timeout=settings.DOWNSTREAM_TIMEOUT)
        if pay_res.status_code != 201:
            order.status = "FAILED"
            order.error_message = f"Payments service returned HTTP {pay_res.status_code}: {pay_res.text}"
            order.save()
            logger.error(f"Payment failed for order {order.id}: {pay_res.text}")
            return Response({"error": order.error_message}, status=status.HTTP_502_BAD_GATEWAY)

        pay_data = pay_res.json()
        order.payment_id = pay_data.get("payment_id")
        order.status = "PAID"
        order.save()
        logger.info(f"Order {order.id} paid successfully.")
        return Response({
            "order_id": str(order.id),
            "status": order.status,
            "payment_id": order.payment_id,
            "total_amount": str(order.total_amount)
        }, status=status.HTTP_201_CREATED)
    except requests.exceptions.RequestException as e:
        order.status = "FAILED"
        order.error_message = f"Downstream payment error: {str(e)}"
        order.save()
        logger.error(f"Downstream dependency timeout or connection failure to Payments: {str(e)}")
        return Response({"error": order.error_message}, status=status.HTTP_504_GATEWAY_TIMEOUT)
