#!/usr/bin/env python3
"""Workflow orchestration helpers for the KWOK perf harness.

This keeps the GitHub Actions steps thin and prints live status while waiting
for workload and controller readiness.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_duration(value: str) -> int:
    value = value.strip().lower()
    if value.endswith("s"):
        return int(value[:-1])
    if value.endswith("m"):
        return int(value[:-1]) * 60
    if value.endswith("h"):
        return int(value[:-1]) * 3600
    return int(value)


def run_cmd(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True)


def kubectl(args: list[str]) -> subprocess.CompletedProcess[str]:
    return run_cmd(["kubectl", *args])


def print_block(title: str, body: str) -> None:
    print(f"[{now_utc()}] {title}", flush=True)
    text = body.rstrip()
    if text:
        print(text, flush=True)


def wait_for_count(resource: str, selector: str, expected: int, timeout: int, interval: int) -> int:
    deadline = datetime.now(timezone.utc) + timedelta(seconds=timeout)
    last_count = -1

    while datetime.now(timezone.utc) < deadline:
        result = kubectl(["get", resource, "-A", "-l", selector, "-o", "name"])
        count = len([line for line in result.stdout.splitlines() if line.strip()]) if result.returncode == 0 else 0
        if count != last_count:
            print(f"[{now_utc()}] workload count {resource}: observed={count} expected={expected}", flush=True)
            last_count = count
        if count == expected:
            return 0
        time.sleep(interval)

    print(f"[{now_utc()}] timed out waiting for {resource} count {expected}, last count={last_count}", file=sys.stderr, flush=True)
    return 1


def deployment_status(namespace: str, name: str) -> tuple[str, dict[str, object] | None]:
    result = kubectl(["get", "deployment", name, "-n", namespace, "-o", "json"])
    if result.returncode != 0:
        return result.stderr.strip() or result.stdout.strip() or "deployment not found", None
    payload = json.loads(result.stdout)
    spec = payload.get("spec", {})
    status = payload.get("status", {})
    conditions = {item.get("type"): item for item in status.get("conditions", []) if isinstance(item, dict)}
    summary = {
        "desired": spec.get("replicas", 0),
        "current": status.get("replicas", 0),
        "updated": status.get("updatedReplicas", 0),
        "available": status.get("availableReplicas", 0),
        "unavailable": status.get("unavailableReplicas", 0),
        "observed_generation": status.get("observedGeneration"),
        "generation": payload.get("metadata", {}).get("generation"),
        "progressing": conditions.get("Progressing", {}).get("status"),
        "available_condition": conditions.get("Available", {}).get("status"),
        "replica_failure": conditions.get("ReplicaFailure", {}).get("status"),
    }
    return "deployment status ready", summary


def globalconfiguration_status() -> tuple[str, str | None]:
    result = kubectl(["get", "globalconfiguration", "global-config", "-o", "json"])
    if result.returncode != 0:
        return result.stderr.strip() or result.stdout.strip() or "globalconfiguration not found", None
    payload = json.loads(result.stdout)
    status = payload.get("status", {})
    conditions = status.get("conditions", [])
    if not isinstance(conditions, list) or not conditions:
        return "globalconfiguration has no conditions", None
    condition_bits = []
    for item in conditions:
        if not isinstance(item, dict):
            continue
        condition_bits.append(f"{item.get('type')}={item.get('status')}")
    return "globalconfiguration conditions", ", ".join(condition_bits) if condition_bits else None


def controller_logs(namespace: str) -> str:
    result = kubectl([
        "logs",
        "-n",
        namespace,
        "-l",
        "control-plane=controller-manager",
        "--since=10m",
        "--tail=40",
        "--all-containers=true",
        "--prefix",
    ])
    if result.returncode != 0:
        return result.stderr.strip() or result.stdout.strip() or "controller logs unavailable"
    return result.stdout.strip() or "controller logs empty"


def controller_pods(namespace: str) -> str:
    result = kubectl(["get", "pod", "-n", namespace, "-o", "wide"])
    return result.stdout.strip() if result.returncode == 0 else (result.stderr.strip() or result.stdout.strip() or "no controller pods")


def controller_pod_node(namespace: str) -> str | None:
    result = kubectl([
        "get",
        "pod",
        "-n",
        namespace,
        "-l",
        "control-plane=controller-manager",
        "-o",
        "json",
    ])
    if result.returncode != 0:
        return None
    payload = json.loads(result.stdout)
    items = payload.get("items", [])
    if not isinstance(items, list) or not items:
        return None
    pod = items[0]
    if not isinstance(pod, dict):
        return None
    return pod.get("spec", {}).get("nodeName")


def node_labels(node_name: str) -> dict[str, str] | None:
    result = kubectl(["get", "node", node_name, "-o", "json"])
    if result.returncode != 0:
        return None
    payload = json.loads(result.stdout)
    labels = payload.get("metadata", {}).get("labels", {})
    return labels if isinstance(labels, dict) else None


def controller_replicasets(namespace: str) -> str:
    result = kubectl(["get", "rs", "-n", namespace, "-o", "wide"])
    return result.stdout.strip() if result.returncode == 0 else (result.stderr.strip() or result.stdout.strip() or "no controller replicasets")


def deployment_yaml(namespace: str, name: str) -> str:
    result = kubectl(["get", "deployment", name, "-n", namespace, "-o", "yaml"])
    return result.stdout.strip() if result.returncode == 0 else (result.stderr.strip() or result.stdout.strip() or "deployment yaml unavailable")


def recent_events(namespace: str) -> str:
    result = kubectl(["get", "events", "-n", namespace, "--sort-by=.lastTimestamp"])
    if result.returncode != 0:
        return result.stderr.strip() or result.stdout.strip() or "events unavailable"
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return "\n".join(lines[-25:]) if lines else "events empty"


def cluster_nodes() -> str:
    result = kubectl(["get", "nodes", "-o", "wide"])
    return result.stdout.strip() if result.returncode == 0 else (result.stderr.strip() or result.stdout.strip() or "nodes unavailable")


def cluster_resources() -> str:
    result = kubectl(["get", "all", "-A", "-o", "wide"])
    return result.stdout.strip() if result.returncode == 0 else (result.stderr.strip() or result.stdout.strip() or "cluster resources unavailable")


def cluster_events() -> str:
    result = kubectl(["get", "events", "-A", "--sort-by=.lastTimestamp"])
    if result.returncode != 0:
        return result.stderr.strip() or result.stdout.strip() or "cluster events unavailable"
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return "\n".join(lines[-40:]) if lines else "cluster events empty"


def cluster_metrics() -> str:
    metrics = []
    nodes = kubectl(["top", "nodes"])
    metrics.append("node metrics:")
    metrics.append(nodes.stdout.strip() if nodes.returncode == 0 else (nodes.stderr.strip() or nodes.stdout.strip() or "node metrics unavailable"))
    pods = kubectl(["top", "pods", "-A"])
    metrics.append("pod metrics:")
    metrics.append(pods.stdout.strip() if pods.returncode == 0 else (pods.stderr.strip() or pods.stdout.strip() or "pod metrics unavailable"))
    return "\n".join(metrics)


def wait_for_controller_health(namespace: str, release: str, timeout: int, interval: int) -> int:
    deadline = datetime.now(timezone.utc) + timedelta(seconds=timeout)
    attempt = 0

    while datetime.now(timezone.utc) < deadline:
        attempt += 1
        dep_msg, dep = deployment_status(namespace, release)
        gc_msg, gc = globalconfiguration_status()
        pods = controller_pods(namespace)
        pod_node = controller_pod_node(namespace)
        pod_node_labels = node_labels(pod_node) if pod_node else None
        on_control_plane = bool(pod_node_labels and ("node-role.kubernetes.io/control-plane" in pod_node_labels or "node-role.kubernetes.io/master" in pod_node_labels))

        print_block(
            f"controller health poll #{attempt}",
            "\n".join(
                [
                    f"deployment: {dep_msg}",
                    json.dumps(dep, sort_keys=True) if dep else dep_msg,
                    f"globalconfiguration: {gc_msg}",
                    gc or gc_msg,
                    "controller pods:",
                    pods,
                    f"controller pod node: {pod_node or 'unknown'}",
                    f"controller pod node labels: {json.dumps(pod_node_labels, sort_keys=True) if pod_node_labels else 'unavailable'}",
                    "controller replicasets:",
                    controller_replicasets(namespace),
                    "recent events:",
                    recent_events(namespace),
                    "deployment yaml:",
                    deployment_yaml(namespace, release),
                    "controller logs:",
                    controller_logs(namespace),
                ]
            ),
        )

        dep_ready = bool(dep and dep.get("available", 0) and dep.get("desired", 0))
        gc_ready = bool(gc and "PodAdmissionWebhookHealthy=True" in gc)
        if dep_ready and gc_ready and on_control_plane:
            print(f"[{now_utc()}] controller health is ready", flush=True)
            return 0

        time.sleep(interval)

    print(f"[{now_utc()}] timed out waiting for controller health", file=sys.stderr, flush=True)
    print_block("final controller pods", controller_pods(namespace))
    print_block("final controller replicasets", controller_replicasets(namespace))
    print_block("cluster nodes", cluster_nodes())
    print_block("cluster metrics", cluster_metrics())
    print_block("cluster resources", cluster_resources())
    print_block("cluster events", cluster_events())
    print_block("final controller logs", controller_logs(namespace))
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    count = subparsers.add_parser("wait-count")
    count.add_argument("--resource", required=True)
    count.add_argument("--selector", required=True)
    count.add_argument("--expected", type=int, required=True)
    count.add_argument("--timeout", default="1800")
    count.add_argument("--interval", type=int, default=5)

    health = subparsers.add_parser("wait-controller-health")
    health.add_argument("--namespace", required=True)
    health.add_argument("--release", required=True)
    health.add_argument("--timeout", default="900")
    health.add_argument("--interval", type=int, default=10)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "wait-count":
        return wait_for_count(args.resource, args.selector, args.expected, parse_duration(args.timeout), args.interval)
    if args.command == "wait-controller-health":
        return wait_for_controller_health(args.namespace, args.release, parse_duration(args.timeout), args.interval)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
