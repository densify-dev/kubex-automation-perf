#!/usr/bin/env python3
"""Generate Helm values, policy CRs, and KWOK workloads for the nightly test."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def yaml_block(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


def render_install_values(cluster_name: str) -> str:
    return yaml_block(
        [
            "createSecrets: false",
            "gateway:",
            "  enabled: false",
            "  configSecretName: kubex-gateway-config",
            "kubex:",
            "  url:",
            "    host: example.invalid",
            "    scheme: https",
            f"  clusterName: {cluster_name}",
            "  recommendationsPath: \"\"",
            "kubexCredentials:",
            "  username: unused",
            "  epassword: unused",
            "metrics:",
            "  enabled: true",
            "  serviceMonitor:",
            "    enabled: false",
            "globalConfiguration:",
            "  enabled: true",
            "  automationEnabled: true",
            "  suppressFetchRecommendations: true",
            "  protectedNamespacePatterns:",
            "    - kube-*",
            "    - openshift-*",
            "policyEvaluation:",
            "  enabled: true",
            "scope: []",
            "policy:",
            "  automationEnabled: true",
            "  defaultPolicy: \"\"",
            "  remoteEnablement: false",
            "  policies: {}",
            "resources:",
            "  requests:",
            "    cpu: 400m",
            "    memory: 4Gi",
            "  limits:",
            "    cpu: 1",
            "    memory: 6Gi",
        ]
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


def render_deployment(namespace: str, index: int) -> str:
    workload_name = f"workload-{index:05d}"
    workload_index = str(index)
    return yaml_block(
        [
            "apiVersion: apps/v1",
            "kind: Deployment",
            "metadata:",
            f"  name: {workload_name}",
            f"  namespace: {namespace}",
            "  labels:",
            "    app.kubernetes.io/name: kwok-perf",
            "    app.kubernetes.io/part-of: kwok-nightly",
            f"    perf.kubex.ai/workload-index: \"{workload_index}\"",
            f"    perf.kubex.ai/namespace: {namespace}",
            "spec:",
            "  replicas: 1",
            "  selector:",
            "    matchLabels:",
            "      app.kubernetes.io/name: kwok-perf",
            f"      perf.kubex.ai/workload-index: \"{workload_index}\"",
            "  template:",
            "    metadata:",
            "      labels:",
            "        app.kubernetes.io/name: kwok-perf",
            "        app.kubernetes.io/part-of: kwok-nightly",
            f"        perf.kubex.ai/workload-index: \"{workload_index}\"",
            f"        perf.kubex.ai/namespace: {namespace}",
            "    spec:",
            "      containers:",
            "        - name: app",
            "          image: registry.k8s.io/pause:3.9",
        ]
    )


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
            parts.append(render_deployment(namespace, index))
        batch_path.write_text("---\n".join(parts), encoding="utf-8")
        batch_files += 1
    return batch_files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--workloads", type=int, default=10000)
    parser.add_argument("--nodes", type=int, default=150)
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--cluster-name", default="kwok-nightly")
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

    (output_dir / "install-values.yaml").write_text(render_install_values(args.cluster_name), encoding="utf-8")
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
        "strategy_name": args.strategy_name,
        "policy_name": args.policy_name,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
