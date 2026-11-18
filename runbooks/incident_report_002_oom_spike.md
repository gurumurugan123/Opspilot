# Incident Report: INC-2026-002 - Payments Service Repeated OOMKilled Restarts

## Summary
On 2026-11-12, the `payments-service` experienced 8 unexpected pod restarts within a 15-minute window following a bulk transaction batch.

## Root Cause
A memory buffer allocation bug was activated during a transaction spike (`TRIGGER_OOM=true`). The pod's memory limit was configured at `10Mi`, which is insufficient for Python Django + Gunicorn runtime overhead, causing the Linux kernel OOM killer to send SIGKILL (exit code 137).

## Evidence Collected
* **Pod Description**: `describe_pod` reported `Last State: Terminated`, `Reason: OOMKilled`, `Exit Code: 137`.
* **Resources**: `limits.memory: 10Mi` was far below standard baseline (`256Mi`).
* **Events**: `Warning Killing container with id ...: Container exceeded its memory limit`.

## Resolution
Updated `payments.yaml` memory limits to `256Mi`. Removed memory leak logic and deployed revision v1.4.3. All pods stabilized immediately.
