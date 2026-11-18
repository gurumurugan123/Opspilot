# Incident Report: INC-2026-003 - Checkout Failure After Deploying Non-Existent Image

## Summary
On 2026-11-14, automated alerts fired for `orders-service` and `payments-service` after a scheduled CI/CD release. New pods could not start, and the deployment remained stuck.

## Root Cause
Jenkins build #48 generated an invalid image tag (`payments-service:v999-does-not-exist`) due to a pipeline script typo. Kubernetes attempted to pull the tag from the registry and failed, leaving new replicas in `ImagePullBackOff`.

## Evidence Collected
* **Pod Status**: `list_pods` showed `payments-service-xxx` in `ImagePullBackOff`.
* **Events**: `Failed to pull image opspilot/payments-service:v999-does-not-exist: manifest unknown`.
* **Deployments**: `get_recent_deployments` showed deployment revision 5 active with unavailable replicas.

## Resolution
Executed rollback: `kubectl rollout undo deployment/payments-service`. Rolled back to revision 4 running image `:latest`. Incident resolved in 4 minutes.
