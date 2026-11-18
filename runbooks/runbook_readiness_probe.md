# Runbook: Investigating Readiness Probe Failures

## 1. Overview
A Readiness Probe tells Kubernetes when a container is ready to accept incoming network traffic. If the probe fails, the pod remains in `Running` state but is removed from the Kubernetes `Service` endpoints.

## 2. Common Symptoms
* Pod status is `Running`, but `Ready` column shows `0/1`.
* Users or upstream services receive HTTP 502 Bad Gateway or 503 Service Unavailable.
* Pod events show `Warning Unhealthy Readiness probe failed: HTTP probe failed with statuscode: 500`.

## 3. Investigation Steps
1. **Check Pod Readiness Status**:
   Run `list_pods(namespace)` and observe `ready` ratio (`0/1`).
2. **Inspect Readiness Probe Specification**:
   Call `describe_pod(pod_name, namespace)`. Check `Readiness: http-get http://:8000/health/`.
3. **Inspect Application Logs**:
   Call `get_pod_logs(pod_name, namespace)`. Check why the `/health/` endpoint returned non-200.
   Verify if `FAIL_READINESS_PROBE=true` was injected or if internal dependencies (DB, Redis) checked by `/health/` are failing.

## 4. Remediation / Suggested Fix
* Fix the failing health check condition (restore database connection or remove artificial probe failure).
* Verify probe path and port match the application's actual listening configuration.
