# Incident Report: INC-2026-001 - Payments Service Database Outage

## Summary
On 2026-11-10, the `payments-service` began returning HTTP 500 errors across all `/api/payments/charge/` endpoints immediately following release v1.4.2.

## Root Cause
A typo was introduced into the deployment ConfigMap `DB_HOST`, setting it to `postgres-wrong-address.internal` instead of `postgres`. Django was unable to resolve the hostname, triggering `OperationalError: could not translate host name` on all connection attempts.

## Evidence Collected
* **Pod Status**: Pods remained in `Running` state because basic HTTP `/health/` did not test database connectivity.
* **Logs**: `psycopg.OperationalError: could not translate host name "postgres-wrong-address.internal" to address: Name or service not known`.
* **Deployments**: Deployment `payments-service` updated 4 minutes prior to alert.

## Resolution
Corrected `DB_HOST` in `payments-config` back to `postgres`. Executed `kubectl rollout restart deployment/payments-service`. Incident resolved in 6 minutes.
