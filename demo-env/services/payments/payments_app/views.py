import os
import time
import logging
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import PaymentTransaction

logger = logging.getLogger(__name__)

# Global memory hog for OOM simulation
_leak_buffer = []

@api_view(["GET"])
def health_check(request):
    """
    Kubernetes Liveness and Readiness Probe endpoint.
    Can be broken via environment variable to test probe failure scenarios.
    """
    if os.getenv("FAIL_READINESS_PROBE", "false").lower() == "true":
        logger.error("Readiness probe artificially failing due to FAIL_READINESS_PROBE=true")
        return Response({"status": "unhealthy", "reason": "probe_failure_injected"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return Response({"status": "healthy", "service": "payments-service"})

@api_view(["POST"])
def charge_payment(request):
    """
    Process a customer payment for an order.
    Includes hooks for controlled fault injection scenarios.
    """
    # Fault Scenario 4: Injected 500 error
    if os.getenv("SIMULATE_500", "false").lower() == "true":
        logger.error("DatabaseConnectionError: could not connect to server: Connection refused on port 5432")
        raise RuntimeError("DatabaseConnectionError: connection pool exhausted or bad DB_HOST")

    # Fault Scenario 2: Injected OOM (Memory leak)
    if os.getenv("TRIGGER_OOM", "false").lower() == "true":
        logger.warning("Simulating memory exhaustion (OOM)...")
        while True:
            _leak_buffer.append(b"A" * 10 * 1024 * 1024) # allocate 10MB chunks repeatedly

    # Fault Scenario 12: Injected CPU throttling spike
    if os.getenv("TRIGGER_CPU_SPIKE", "false").lower() == "true":
        logger.warning("Simulating heavy CPU computation spike...")
        start = time.time()
        while time.time() - start < 15:
            _ = [x**2 for x in range(100000)]

    # Fault Scenario 6: Injected slow query
    if os.getenv("SIMULATE_SLOW_QUERY", "false").lower() == "true":
        logger.warning("Simulating slow database query latency...")
        time.sleep(5)

    order_id = request.data.get("order_id")
    amount = request.data.get("amount")

    if not order_id or not amount:
        return Response({"error": "order_id and amount are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        tx = PaymentTransaction.objects.create(
            order_id=str(order_id),
            amount=amount,
            status="COMPLETED"
        )
        logger.info(f"Successfully processed payment {tx.id} for order {order_id}")
        return Response({
            "payment_id": str(tx.id),
            "order_id": tx.order_id,
            "amount": str(tx.amount),
            "status": tx.status
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.exception(f"Payment failed with error: {str(e)}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["GET"])
def list_payments(request):
    payments = PaymentTransaction.objects.all().order_by("-created_at")[:50]
    data = [
        {"id": str(p.id), "order_id": p.order_id, "amount": str(p.amount), "status": p.status, "created_at": p.created_at}
        for p in payments
    ]
    return Response(data)
