#!/usr/bin/env python3
"""Count final benchmark resources without serializing expensive API listings."""

from __future__ import annotations

import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor


SELECTOR = "app.kubernetes.io/name=kwok-perf"


def kubectl_names(args: list[str], timeout: int) -> list[str] | None:
    try:
        result = subprocess.run(
            ["kubectl", "get", *args, "-o", "name"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def collect_counts(namespace: str, timeout: int) -> dict[str, int | None]:
    queries = {
        "workloads": ["deploy,statefulsets,cronjobs,daemonsets", "-A", "-l", SELECTOR],
        "pods": ["pod", "-A", "-l", SELECTOR],
        "replicasets": ["rs", "-A", "-l", SELECTOR],
        "controller_pods": ["pod", "-n", namespace, "-l", "control-plane=controller-manager"],
    }
    with ThreadPoolExecutor(max_workers=len(queries)) as executor:
        futures = {
            key: executor.submit(kubectl_names, args, timeout)
            for key, args in queries.items()
        }
        results = {key: future.result() for key, future in futures.items()}

    workloads = results["workloads"]
    counts: dict[str, int | None] = {
        "deployments": None,
        "statefulsets": None,
        "cronjobs": None,
        "daemonsets": None,
        "pods": None if results["pods"] is None else len(results["pods"]),
        "replicasets": None if results["replicasets"] is None else len(results["replicasets"]),
        "controller_pods": None if results["controller_pods"] is None else len(results["controller_pods"]),
    }
    if workloads is not None:
        prefixes = {
            "deployments": "deployment.apps/",
            "statefulsets": "statefulset.apps/",
            "cronjobs": "cronjob.batch/",
            "daemonsets": "daemonset.apps/",
        }
        for key, prefix in prefixes.items():
            counts[key] = sum(name.startswith(prefix) for name in workloads)
        counts["workloads"] = len(workloads)
    else:
        counts["workloads"] = None
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()

    for key, value in collect_counts(args.namespace, args.timeout).items():
        print(f"{key}={value if value is not None else 'unavailable'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
