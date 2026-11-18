import os
import logging
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
import redis

logger = logging.getLogger(__name__)

# In-memory stock store for local standalone fallback
_MOCK_STOCK = {
    "item_101": 50,
    "item_102": 15,
    "item_103": 0,
}

def get_redis_client():
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        socket_connect_timeout=2,
        decode_responses=True
    )

@api_view(["GET"])
def health_check(request):
    """
    Kubernetes health check endpoint.
    Fails if FAIL_READINESS_PROBE=true.
    """
    if os.getenv("FAIL_READINESS_PROBE", "false").lower() == "true":
        logger.error("Inventory readiness probe failing artificially.")
        return Response({"status": "unhealthy"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return Response({"status": "healthy", "service": "inventory-service"})

@api_view(["GET"])
def check_stock(request, item_id):
    """
    Check stock availability for an item.
    Queries Redis cache first.
    """
    # Fault Scenario 7: Injected Redis connection failure
    strict_redis = os.getenv("REQUIRE_REDIS", "false").lower() == "true"
    
    try:
        r = get_redis_client()
        cached_stock = r.get(f"stock:{item_id}")
        if cached_stock is not None:
            stock = int(cached_stock)
        else:
            stock = _MOCK_STOCK.get(item_id, 20)
            r.setex(f"stock:{item_id}", 300, stock)
    except Exception as e:
        logger.error(f"Redis error: {str(e)}")
        if strict_redis:
            # Raise unhandled error so incident investigator can spot Redis failure in logs
            raise ConnectionError(f"CRITICAL: Failed to connect to Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT} - Connection Refused")
        # Graceful fallback to mock stock if not strict
        stock = _MOCK_STOCK.get(item_id, 20)

    return Response({
        "item_id": item_id,
        "available_quantity": stock,
        "in_stock": stock > 0
    })

@api_view(["POST"])
def reserve_stock(request, item_id):
    """Reserve or decrement stock for an order."""
    quantity = int(request.data.get("quantity", 1))
    
    try:
        r = get_redis_client()
        r.decrby(f"stock:{item_id}", quantity)
    except Exception as e:
        logger.warning(f"Could not decrement in Redis: {e}")

    return Response({
        "item_id": item_id,
        "status": "RESERVED",
        "reserved_quantity": quantity
    })
