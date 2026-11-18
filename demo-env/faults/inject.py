#!/usr/bin/env python
"""
OpsPilot Fault Injection CLI:
Injects specific, reproducible incident scenarios into the Kubernetes cluster.
"""

import sys
import argparse
import subprocess

NAMESPACE = "opspilot-demo"

def run_cmd(cmd: list):
    print(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error: {res.stderr.strip()}", file=sys.stderr)
    else:
        print(res.stdout.strip())
    return res

def inject_crashloop():
    """Scenario 1: Missing or wrong environment variable (CrashLoopBackOff)."""
    print("\n[Injecting Scenario 1: CrashLoopBackOff on payments-service]")
    run_cmd([
        "kubectl", "set", "env", "deployment/payments-service",
        "SIMULATE_STARTUP_CRASH=true",
        "-n", NAMESPACE
    ])

def inject_oomkilled():
    """Scenario 2: Memory limit too low / memory leak (OOMKilled)."""
    print("\n[Injecting Scenario 2: OOMKilled on payments-service]")
    # Drop memory limit to 10Mi and trigger leak
    run_cmd([
        "kubectl", "set", "resources", "deployment/payments-service",
        "--limits=memory=10Mi",
        "-n", NAMESPACE
    ])
    run_cmd([
        "kubectl", "set", "env", "deployment/payments-service",
        "TRIGGER_OOM=true",
        "-n", NAMESPACE
    ])

def inject_imagepullbackoff():
    """Scenario 3: Non-existent image tag (ImagePullBackOff)."""
    print("\n[Injecting Scenario 3: ImagePullBackOff on payments-service]")
    run_cmd([
        "kubectl", "set", "image", "deployment/payments-service",
        "payments-service=opspilot/payments-service:v999-does-not-exist",
        "-n", NAMESPACE
    ])

def inject_bad_db_host():
    """Scenario 4: 500 errors after deploy due to invalid DB_HOST."""
    print("\n[Injecting Scenario 4: Bad DB_HOST on payments-service]")
    run_cmd([
        "kubectl", "set", "env", "deployment/payments-service",
        "DB_HOST=postgres-wrong-address.internal",
        "SIMULATE_500=true",
        "-n", NAMESPACE
    ])

def inject_readiness_probe_failing():
    """Scenario 5: Readiness probe failing (endpoint returns 500)."""
    print("\n[Injecting Scenario 5: Readiness probe failing on inventory-service]")
    run_cmd([
        "kubectl", "set", "env", "deployment/inventory-service",
        "FAIL_READINESS_PROBE=true",
        "-n", NAMESPACE
    ])

def inject_redis_refused():
    """Scenario 7: Redis connection refused."""
    print("\n[Injecting Scenario 7: Redis connection refused on inventory-service]")
    run_cmd([
        "kubectl", "set", "env", "deployment/inventory-service",
        "REDIS_HOST=unreachable-redis.internal",
        "REQUIRE_REDIS=true",
        "-n", NAMESPACE
    ])

def inject_pending_pod():
    """Scenario 9: Deployment stuck (Pending pod due to impossible resources)."""
    print("\n[Injecting Scenario 9: Pending pod due to impossible resource limits]")
    run_cmd([
        "kubectl", "set", "resources", "deployment/orders-service",
        "--requests=cpu=1000,memory=1000Gi",
        "-n", NAMESPACE
    ])

def inject_downstream_timeout():
    """Scenario 14: Downstream dependency timeout."""
    print("\n[Injecting Scenario 14: Downstream dependency timeout on orders-service]")
    run_cmd([
        "kubectl", "set", "env", "deployment/orders-service",
        "DOWNSTREAM_TIMEOUT=0.001",
        "-n", NAMESPACE
    ])

SCENARIOS = {
    "crashloop": inject_crashloop,
    "oomkilled": inject_oomkilled,
    "imagepull": inject_imagepullbackoff,
    "bad_db_host": inject_bad_db_host,
    "readiness_fail": inject_readiness_probe_failing,
    "redis_refused": inject_redis_refused,
    "pending_pod": inject_pending_pod,
    "downstream_timeout": inject_downstream_timeout,
}

def main():
    parser = argparse.ArgumentParser(description="OpsPilot Fault Injector")
    parser.add_argument("scenario", choices=list(SCENARIOS.keys()) + ["list"], help="Scenario to inject")
    args = parser.parse_args()

    if args.scenario == "list":
        print("Available fault injection scenarios:")
        for name in SCENARIOS:
            print(f"  - {name}")
        return

    handler = SCENARIOS.get(args.scenario)
    if handler:
        handler()
        print(f"\nFault '{args.scenario}' injected. Check status with: kubectl get pods -n {NAMESPACE}")
        print("To reset environment, run: python demo-env/faults/reset.py")

if __name__ == "__main__":
    main()
