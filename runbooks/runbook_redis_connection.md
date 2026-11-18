# Runbook: Investigating Redis Connection Refused Outages

## 1. Overview
When a microservice fails to connect to Redis, caching, session storage, and rate-limiting operations fail. Services configured with strict cache dependency will return HTTP 500 errors.

## 2. Common Symptoms
* Log entries containing `redis.exceptions.ConnectionError: Error 111 connecting to redis: Connection refused` or `Name or service not known`.
* Degraded API response times or elevated HTTP 500 rates on inventory/caching endpoints.

## 3. Investigation Steps
1. **Search Logs for Redis Exceptions**:
   Call `get_pod_logs(pod_name, namespace)`. Filter for `Connection refused` or `redis.exceptions`.
2. **Check Redis Pod Status**:
   Call `list_pods(namespace)`. Confirm the `redis` pod is in `Running` state and has not restarted.
3. **Verify Environment Configuration**:
   Inspect ConfigMaps for `REDIS_HOST` and `REDIS_PORT`. Ensure `REDIS_HOST` matches the internal Kubernetes Service name (`redis`).

## 4. Remediation / Suggested Fix
* If the Redis pod crashed, check Redis pod logs and restart the deployment.
* If `REDIS_HOST` is pointing to an invalid hostname, update the ConfigMap and restart the consumer pods.
