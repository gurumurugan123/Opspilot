"""
Structured JSON Request Logging Middleware for OpsPilot Backend.

Attaches a unique `X-Request-ID` to every HTTP request/response and logs
status codes, duration, user-agent, and client IP in structured JSON format.
"""

import json
import logging
import time
import uuid

logger = logging.getLogger("opspilot.api")


class StructuredLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.request_id = request_id
        start_time = time.time()

        response = self.get_response(request)

        duration_ms = round((time.time() - start_time) * 1000.0, 2)
        response["X-Request-ID"] = request_id

        log_record = {
            "request_id": request_id,
            "method": request.method,
            "path": request.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "remote_addr": request.META.get("REMOTE_ADDR", ""),
        }

        if response.status_code >= 500:
            logger.error(json.dumps(log_record))
        elif response.status_code >= 400:
            logger.warning(json.dumps(log_record))
        else:
            logger.info(json.dumps(log_record))

        return response
