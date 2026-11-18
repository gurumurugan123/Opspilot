# Runbook: Investigating OOMKilled Containers

## 1. Overview
When a container exceeds the memory limit declared in its Kubernetes pod specification (`resources.limits.memory`), the Linux kernel OOM (Out Of Memory) killer sends a `SIGKILL` (exit code 137) to the process.

## 2. Common Symptoms
* Pod restarts intermittently.
* `describe_pod` shows `Reason: OOMKilled` and `Exit Code: 137`.
* Kubernetes events show `Killing container with id ...: Container exceeded its memory limit`.

## 3. Investigation Steps
1. **Confirm Termination Reason**:
   Call `describe_pod(pod_name, namespace)`. Check `Last State -> Terminated -> Reason`. If it says `OOMKilled`, memory exhaustion is confirmed.
2. **Review Resource Allocations**:
   Check `resources.limits.memory` for the container. Compare against typical application heap requirements (e.g., Python Django apps typically need $\ge 128\text{MiB}$).
3. **Inspect Application Logs**:
   Look for large data processing loops, bulk object loads from database without pagination, or memory leak patterns before the restart timestamp.

## 4. Remediation / Suggested Fix
* Temporary emergency fix: Increase the pod memory limit:
  `kubectl set resources deployment/<service> --limits=memory=512Mi -n <namespace>`
* Permanent fix: Investigate memory leak in application code, optimize query pagination, or tune Gunicorn worker recycling (`--max-requests`).
