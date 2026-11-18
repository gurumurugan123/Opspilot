# Runbook: Investigating Downstream Dependency Timeouts

## 1. Overview
When a service (such as `orders-service`) calls an upstream/downstream service (`payments-service` or `inventory-service`) and the response is not received within the configured timeout window, the calling service aborts the request and returns HTTP 504 Gateway Timeout.

## 2. Common Symptoms
* Spikes in HTTP 504 Gateway Timeout or 502 Bad Gateway responses.
* Application logs show `requests.exceptions.ConnectTimeout` or `requests.exceptions.ReadTimeout`.
* High response latency on client-facing API endpoints.

## 3. Investigation Steps
1. **Identify the Calling and Target Services**:
   Call `get_pod_logs("orders-service-...", namespace)`. Extract the target URL that timed out.
2. **Inspect Target Service Health**:
   Check if the downstream service is healthy or suffering from high CPU throttling, slow DB queries, or high restart counts.
3. **Verify Timeout Settings**:
   Check `DOWNSTREAM_TIMEOUT` in the calling service's ConfigMap. An unrealistically low timeout (e.g., 1ms) will cause every request to fail.

## 4. Remediation / Suggested Fix
* Restore appropriate timeout values (`DOWNSTREAM_TIMEOUT=3.0` or higher).
* Scale out replicas of the downstream service or resolve database bottlenecks causing latency.
