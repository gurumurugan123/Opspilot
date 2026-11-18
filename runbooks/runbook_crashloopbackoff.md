# Runbook: Investigating Pods in CrashLoopBackOff

## 1. Overview
A `CrashLoopBackOff` status indicates that a container started, crashed or exited with an error code, and Kubernetes is attempting to restart it with exponential backoff delay.

## 2. Common Symptoms
* `kubectl get pods` shows status `CrashLoopBackOff` or `Error`.
* Pod restart count increases rapidly.
* HTTP 500 or 502 errors when upstream services make requests to the failing service.

## 3. Investigation Steps
1. **Check Pod Events & Exit Code**:
   Run `describe_pod(pod_name, namespace)` to inspect `Last State`, `Exit Code`, and termination reason.
   * `Exit Code 1`: General application exception or unhandled error.
   * `Exit Code 137`: Process killed by SIGKILL (often OOMKilled).
2. **Inspect Container Logs**:
   Run `get_pod_logs(pod_name, namespace, tail_lines=50)` with focus on the last lines before exit.
   Look for:
   * `KeyError` or missing required environment variables (e.g. `DB_PASSWORD`, `SECRET_KEY`).
   * Syntax errors or import failures during startup.
   * Startup crashes caused by `SIMULATE_STARTUP_CRASH=true`.
3. **Verify Configuration**:
   Inspect ConfigMaps and Secrets referenced in the pod's `env` and `envFrom` specifications.

## 4. Remediation / Suggested Fix
* If caused by a missing environment variable, add the missing variable to the respective `Secret` or `ConfigMap` and trigger a rollout restart.
* If caused by a code regression, rollback deployment: `kubectl rollout undo deployment/<service-name>`.
