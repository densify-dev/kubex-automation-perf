#!/usr/bin/env python3
"""Generate Helm values, policy CRs, and mixed KWOK workloads for the nightly test."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import textwrap


def yaml_block(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


def render_install_values(kubex_host: str, kubex_cluster_name: str) -> str:
    return textwrap.dedent(
        f"""\
        createSecrets: true
        gateway:
          enabled: false
          configSecretName: kubex-gateway-config
        kubex:
          url:
            host: '{kubex_host}'
            scheme: https
          clusterName: '{kubex_cluster_name}'
          recommendationsPath: ""
        metrics:
          enabled: true
          serviceMonitor:
            enabled: false
        globalConfiguration:
          enabled: true
          automationEnabled: true
          suppressFetchRecommendations: true
          protectedNamespacePatterns:
            - kube-*
            - openshift-*
        policyEvaluation:
          enabled: true
        scope: []
        policy:
          automationEnabled: true
          defaultPolicy: ""
          remoteEnablement: false
          policies: {{}}
        resources:
          requests:
            cpu: 400m
            memory: 4Gi
          limits:
            cpu: "1"
            memory: 6Gi
        nodeSelector:
          node-role.kubernetes.io/control-plane: ""
        tolerations:
          - key: "kubernetes.io/arch"
            operator: "Exists"
            effect: "NoSchedule"
          - key: "node-role.kubernetes.io/control-plane"
            operator: "Exists"
            effect: "NoSchedule"
        """
    )


def render_namespace(name: str) -> str:
    return yaml_block(
        [
            "apiVersion: v1",
            "kind: Namespace",
            "metadata:",
            f"  name: {name}",
        ]
    )


def render_strategy(name: str) -> str:
    return yaml_block(
        [
            "apiVersion: rightsizing.kubex.ai/v1alpha1",
            "kind: ClusterAutomationStrategy",
            "metadata:",
            f"  name: {name}",
            "spec: {}",
        ]
    )


def render_policy(name: str, strategy_name: str, namespaces: list[str]) -> str:
    lines = [
        "apiVersion: rightsizing.kubex.ai/v1alpha1",
        "kind: ClusterStaticPolicy",
        "metadata:",
        f"  name: {name}",
        "spec:",
        "  scope:",
        "    labelSelector:",
        "      matchLabels:",
        "        app.kubernetes.io/name: kwok-perf",
        "    workloadTypes:",
        "      - Deployment",
        "      - StatefulSet",
        "      - CronJob",
        "      - DaemonSet",
        "    namespaceSelector:",
        "      operator: In",
        "      values:",
    ]
    lines.extend([f"        - {namespace}" for namespace in namespaces])
    lines.extend(
        [
            "  resources:",
            "    containers:",
            '      "*":',
            "        requests:",
            "          cpu: 250m",
            "          memory: 256Mi",
            "        limits:",
            "          cpu: 500m",
            "          memory: 512Mi",
            "  weight: 100",
            "  automationStrategyRef:",
            f"    name: {strategy_name}",
        ]
    )
    return yaml_block(lines)


def workload_kind(index: int) -> str:
    if index % 200 == 0:
        return "DaemonSet"
    kinds = ["Deployment", "StatefulSet", "CronJob"]
    return kinds[(index - 1) % len(kinds)]


def workload_kind_counts(total: int) -> dict[str, int]:
    counts = {"Deployment": 0, "StatefulSet": 0, "CronJob": 0, "DaemonSet": 0}
    for index in range(1, total + 1):
        counts[workload_kind(index)] += 1
    return counts


def workload_labels(namespace: str, index: int, indent: int) -> list[str]:
    prefix = " " * indent
    return [
        f"{prefix}app.kubernetes.io/name: kwok-perf",
        f"{prefix}app.kubernetes.io/part-of: kwok-nightly",
        f"{prefix}perf.kubex.ai/workload-index: \"{index}\"",
        f"{prefix}perf.kubex.ai/namespace: {namespace}",
    ]


def workload_scheduling(indent: int) -> list[str]:
    prefix = " " * indent
    return [
        f"{prefix}affinity:",
        f"{prefix}  nodeAffinity:",
        f"{prefix}    requiredDuringSchedulingIgnoredDuringExecution:",
        f"{prefix}      nodeSelectorTerms:",
        f"{prefix}        - matchExpressions:",
        f"{prefix}          - key: type",
        f"{prefix}            operator: In",
        f"{prefix}            values:",
        f"{prefix}              - kwok",
        f"{prefix}tolerations:",
        f"{prefix}  - key: kwok.x-k8s.io/node",
        f"{prefix}    operator: Exists",
        f"{prefix}    effect: NoSchedule",
    ]


def render_workload(namespace: str, index: int, kind: str) -> str:
    workload_name = f"workload-{index:05d}"

    if kind == "Deployment":
        return yaml_block(
            [
                "apiVersion: apps/v1",
                "kind: Deployment",
                "metadata:",
                f"  name: {workload_name}",
                f"  namespace: {namespace}",
                "  labels:",
                *workload_labels(namespace, index, 4),
                "spec:",
                "  replicas: 1",
                "  selector:",
                "    matchLabels:",
                "      app.kubernetes.io/name: kwok-perf",
                f"      perf.kubex.ai/workload-index: \"{index}\"",
                "  template:",
                "    metadata:",
                "      labels:",
                *workload_labels(namespace, index, 8),
                "    spec:",
                "      containers:",
                "        - name: app",
                "          image: registry.k8s.io/pause:3.9",
                *workload_scheduling(6),
            ]
        )

    if kind == "StatefulSet":
        return yaml_block(
            [
                "apiVersion: apps/v1",
                "kind: StatefulSet",
                "metadata:",
                f"  name: {workload_name}",
                f"  namespace: {namespace}",
                "  labels:",
                *workload_labels(namespace, index, 4),
                "spec:",
                f"  serviceName: {workload_name}",
                "  replicas: 1",
                "  selector:",
                "    matchLabels:",
                "      app.kubernetes.io/name: kwok-perf",
                f"      perf.kubex.ai/workload-index: \"{index}\"",
                "  template:",
                "    metadata:",
                "      labels:",
                *workload_labels(namespace, index, 8),
                "    spec:",
                "      containers:",
                "        - name: app",
                "          image: registry.k8s.io/pause:3.9",
                *workload_scheduling(6),
            ]
        )

    if kind == "CronJob":
        return yaml_block(
            [
                "apiVersion: batch/v1",
                "kind: CronJob",
                "metadata:",
                f"  name: {workload_name}",
                f"  namespace: {namespace}",
                "  labels:",
                *workload_labels(namespace, index, 4),
                "spec:",
                "  schedule: \"*/5 * * * *\"",
                "  suspend: true",
                "  jobTemplate:",
                "    spec:",
                "      template:",
                "        metadata:",
                "          labels:",
                *workload_labels(namespace, index, 12),
                "        spec:",
                "          restartPolicy: Never",
                *workload_scheduling(10),
                "          containers:",
                "            - name: app",
                "              image: registry.k8s.io/pause:3.9",
            ]
        )

    if kind == "DaemonSet":
        return yaml_block(
            [
                "apiVersion: apps/v1",
                "kind: DaemonSet",
                "metadata:",
                f"  name: {workload_name}",
                f"  namespace: {namespace}",
                "  labels:",
                *workload_labels(namespace, index, 4),
                "spec:",
                "  selector:",
                "    matchLabels:",
                "      app.kubernetes.io/name: kwok-perf",
                f"      perf.kubex.ai/workload-index: \"{index}\"",
                "  template:",
                "    metadata:",
                "      labels:",
                *workload_labels(namespace, index, 8),
                "    spec:",
                "      containers:",
                "        - name: app",
                "          image: registry.k8s.io/pause:3.9",
                *workload_scheduling(6),
            ]
        )

    raise ValueError(f"unsupported workload kind: {kind}")


def write_batches(output_dir: Path, namespaces: list[str], workloads: int, batch_size: int) -> int:
    batch_dir = output_dir / "workloads"
    batch_dir.mkdir(parents=True, exist_ok=True)
    batch_files = 0
    for start in range(1, workloads + 1, batch_size):
        end = min(start + batch_size - 1, workloads)
        batch_path = batch_dir / f"batch-{batch_files:03d}.yaml"
        parts: list[str] = []
        for index in range(start, end + 1):
            namespace = namespaces[(index - 1) % len(namespaces)]
            parts.append(render_workload(namespace, index, workload_kind(index)))
        batch_path.write_text("---\n".join(parts), encoding="utf-8")
        batch_files += 1
    return batch_files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--workloads", type=int, default=50000)
    parser.add_argument("--nodes", type=int, default=450)
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--cluster-name", default="kwok-nightly")
    parser.add_argument("--kubex-host", default="automationtest.kubex.ai")
    parser.add_argument("--kubex-cluster-name", default="automation-perf-test")
    parser.add_argument("--release-name", default="kubex-automation-engine")
    parser.add_argument("--release-namespace", default="kubex")
    parser.add_argument("--namespace-prefix", default="perf")
    parser.add_argument("--strategy-name", default="perf-static-strategy")
    parser.add_argument("--policy-name", default="perf-static-policy")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "workloads").mkdir(exist_ok=True)

    namespace_count = max(1, min(args.nodes // 15 or 1, 10))
    namespaces = [f"{args.namespace_prefix}-{idx:02d}" for idx in range(1, namespace_count + 1)]

    (output_dir / "install-values.yaml").write_text(
        render_install_values(args.kubex_host, args.kubex_cluster_name), encoding="utf-8"
    )
    (output_dir / "namespaces.yaml").write_text("---\n".join(render_namespace(name) for name in namespaces), encoding="utf-8")
    (output_dir / "strategy.yaml").write_text(render_strategy(args.strategy_name), encoding="utf-8")
    (output_dir / "policy.yaml").write_text(
        render_policy(args.policy_name, args.strategy_name, namespaces), encoding="utf-8"
    )
    batch_files = write_batches(output_dir, namespaces, args.workloads, args.batch_size)

    metadata = {
        "cluster_name": args.cluster_name,
        "release_name": args.release_name,
        "release_namespace": args.release_namespace,
        "workloads": args.workloads,
        "nodes": args.nodes,
        "namespaces": namespaces,
        "namespace_count": len(namespaces),
        "batch_size": args.batch_size,
        "batch_files": batch_files,
        "workload_kind_counts": workload_kind_counts(args.workloads),
        "strategy_name": args.strategy_name,
        "policy_name": args.policy_name,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
