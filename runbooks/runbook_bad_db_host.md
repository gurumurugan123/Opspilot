# Runbook: Investigating 500 Errors and Database Connection Failures

## 1. Overview
When a service fails to connect to its backing database (PostgreSQL), incoming requests return HTTP 500 Internal Server Error or HTTP 502 Bad Gateway to upstream consumers.

## 2. Common Symptoms
* Spikes in HTTP 500 error rates on API endpoints.
* Application logs show `django.db.utils.OperationalError: could not translate host name` or `connection refused`.
* Health checks fail if database readiness checks are enabled.

## 3. Investigation Steps
1. **Inspect Application Logs**:
   Call `get_pod_logs(pod_name, namespace)`. Check for:
   * `psycopg.OperationalError` or `django.db.utils.OperationalError`.
   * Connection refused on port 5432.
   * `could not translate host name "..."`.
2. **Check Deployment Configuration**:
   Inspect the environment variables `DB_HOST`, `DB_PORT`, and `DB_NAME`.
   Verify whether `DB_HOST` points to the correct internal Kubernetes Service (e.g. `postgres` or `postgres.opspilot-demo.svc.cluster.local`).
3. **Verify Database Pod Health**:
   Check if the database pod is running and accepting connections:
   `list_pods(namespace)` $\to$ confirm `postgres` pod status is `Running`.

## 4. Remediation / Suggested Fix
* Update the ConfigMap `payments-config` with the correct `DB_HOST: "postgres"`.
* Re-apply config and perform a rollout restart.
