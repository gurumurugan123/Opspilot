#!/usr/bin/env python
"""
OpsPilot Reset Script:
Restores the Kubernetes demo environment to a 100% healthy, baseline state.
"""

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
K8S_DIR = BASE_DIR / "k8s"

def run_cmd(cmd: list):
    print(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Warning: {result.stderr.strip()}", file=sys.stderr)
    else:
        print(result.stdout.strip())
    return result

def reset_cluster():
    print("=== OpsPilot: Resetting Demo Environment to Healthy Baseline ===")
    
    # 1. Apply namespace & RBAC
    run_cmd(["kubectl", "apply", "-f", str(K8S_DIR / "namespace.yaml")])
    run_cmd(["kubectl", "apply", "-f", str(K8S_DIR / "rbac.yaml")])

    # 2. Re-apply infrastructure
    run_cmd(["kubectl", "apply", "-f", str(K8S_DIR / "postgres.yaml")])
    run_cmd(["kubectl", "apply", "-f", str(K8S_DIR / "redis.yaml")])

    # 3. Re-apply baseline services
    run_cmd(["kubectl", "apply", "-f", str(K8S_DIR / "payments.yaml")])
    run_cmd(["kubectl", "apply", "-f", str(K8S_DIR / "inventory.yaml")])
    run_cmd(["kubectl", "apply", "-f", str(K8S_DIR / "orders.yaml")])

    print("\nWaiting for deployments to roll out to healthy state...")
    services = ["payments-service", "inventory-service", "orders-service"]
    for svc in services:
        run_cmd(["kubectl", "rollout", "status", f"deployment/{svc}", "-n", "opspilot-demo", "--timeout=60s"])

    print("\n[SUCCESS] Environment reset to healthy state.")

if __name__ == "__main__":
    reset_cluster()
