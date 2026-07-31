#!/usr/bin/env python3
"""Count final benchmark resources without serializing expensive API listings."""

from __future__ import annotations

import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor


WORKLOAD_SELECTOR = "app.kubernetes.io/name=kwok-perf"
POD_QUERY = ["pod", "-A", "-l", WORKLOAD_SELECTOR]


def kubectl_count(args: list[str], timeout: int) -> int | None:
    try:
        result = subprocess.run(
            ["kubectl", "get", *args, "--no-headers", f"--request-timeout={timeout}s"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    return sum(1 for line in result.stdout.splitlines() if line.strip())


def collect_counts(namespace: str, timeout: int) -> dict[str, int | None]:
    queries = {
        "deployments": ["deploy", "-A", "-l", WORKLOAD_SELECTOR],
        "statefulsets": ["statefulsets", "-A", "-l", WORKLOAD_SELECTOR],
        "cronjobs": ["cronjobs", "-A", "-l", WORKLOAD_SELECTOR],
        "daemonsets": ["daemonsets", "-A", "-l", WORKLOAD_SELECTOR],
        "pods": POD_QUERY,
        "replicasets": ["rs", "-A", "-l", WORKLOAD_SELECTOR],
        "controller_pods": ["pod", "-n", namespace, "-l", "control-plane=controller-manager"],
    }
    with ThreadPoolExecutor(max_workers=len(queries)) as executor:
        futures = {
            key: executor.submit(kubectl_count, args, timeout)
            for key, args in queries.items()
        }
        counts = {key: future.result() for key, future in futures.items()}

    workload_counts = [counts[key] for key in ("deployments", "statefulsets", "cronjobs", "daemonsets")]
    counts["workloads"] = sum(workload_counts) if all(value is not None for value in workload_counts) else None
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--pods-only", action="store_true")
    args = parser.parse_args()

    counts = (
        {"pods": kubectl_count(POD_QUERY, args.timeout)}
        if args.pods_only
        else collect_counts(args.namespace, args.timeout)
    )
    for key, value in counts.items():
        print(f"{key}={value if value is not None else 'unavailable'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
