# Runbook: Investigating High CPU Throttling and Latency Spikes

## 1. Overview
When a container consumes more CPU than its Kubernetes `resources.limits.cpu` allows, the Linux CFS (Completely Fair Scheduler) throttles the container's CPU quota. The container does not crash, but processing becomes extremely slow, leading to request queuing and timeouts.

## 2. Common Symptoms
* Latency increases significantly on API endpoints while pod memory and network remain low.
* Prometheus metrics show elevated `container_cpu_cfs_throttled_periods_total`.
* Upstream callers experience downstream timeouts.

## 3. Investigation Steps
1. **Inspect CPU Limits**:
   Call `describe_pod(pod_name, namespace)`. Check `resources.limits.cpu`. (e.g. 50m is only 0.05 CPU core).
2. **Review Application Logs**:
   Look for CPU-intensive loops, unindexed queries, or batch computations running on the main request thread.
3. **Correlate with Recent Releases**:
   Check `get_recent_deployments(namespace)` to determine if a recent deployment lowered CPU limits or introduced unoptimized algorithms.

## 4. Remediation / Suggested Fix
* Increase container CPU limit (e.g. to `500m` or `1000m`).
* Offload CPU-heavy tasks to asynchronous Celery background workers.
