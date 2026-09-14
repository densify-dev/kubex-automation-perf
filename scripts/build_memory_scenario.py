#!/usr/bin/env python3
"""Generate a version-pinned scenario for the release memory benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from scripts import build_scenario
except ModuleNotFoundError:
    import build_scenario


RELEASES = ("1.8.0", "1.9.0", "1.9.1", "1.10.0", "1.11.0", "1.11.1", "1.11.2")
COMPACTION_FIRST_RELEASE = (1, 10, 0)


def version_tuple(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError as exc:
        raise ValueError(f"invalid release version: {version}") from exc


def crd_version_for(release: str) -> str:
    if release == "1.9.1":
        return "1.9.0"
    return release


def compaction_supported(release: str) -> bool:
    return version_tuple(release) >= COMPACTION_FIRST_RELEASE


def render_compaction_policy(name: str, namespaces: list[str]) -> str:
    lines = [
        "apiVersion: rightsizing.kubex.ai/v1alpha1",
        "kind: ClusterCompactionPolicy",
        "metadata:",
        f"  name: {name}",
        "spec:",
        "  scope:",
        "    labelSelector:",
        "      matchLabels:",
        "        app.kubernetes.io/name: kwok-perf",
        "    namespaceSelector:",
        "      operator: In",
        "      values:",
    ]
    lines.extend(f"        - {namespace}" for namespace in namespaces)
    lines.extend(
        [
            "    workloadTypes:",
            "      - Deployment",
            "      - StatefulSet",
            "  enabled: true",
            "  setLabelsByEviction: true",
            "  scheduler:",
            "    useKubexScheduler: true",
            "  descheduler:",
            "    enabled: true",
            '    interval: "*/2 * * * *"',
            "    maxNoOfPodsToEvictPerNode: 1",
            "    maxNoOfPodsToEvictPerNamespace: 1",
            "    maxNoOfPodsToEvictTotal: 10",
            "    highNodeUtilization:",
            "      numberOfNodes: 1",
            "      thresholds:",
            "        cpu: 25",
            "        memory: 25",
            "        pods: 25",
        ]
    )
    return build_scenario.yaml_block(lines)


def render_values(kubex_host: str, cluster_name: str, release: str, mode: str) -> str:
    values = build_scenario.render_install_values(kubex_host, cluster_name)
    if not compaction_supported(release):
        return values
    enabled = "true" if mode == "active" else "false"
    return values + f"\ncompactionScheduler:\n  enabled: {enabled}\ncompactionDescheduler:\n  enabled: {enabled}\n"


def render_configmap(namespace: str, index: int, payload: str) -> str:
    lines = [
        "apiVersion: v1",
        "kind: ConfigMap",
        "metadata:",
        f"  name: perf-config-{index:06d}",
        f"  namespace: {namespace}",
        "  labels:",
        "    app.kubernetes.io/name: kwok-perf-config",
        "data:",
        f"  payload: {payload}",
    ]
    return build_scenario.yaml_block(lines)


def write_configmap_batches(output_dir: Path, namespaces: list[str], count: int, batch_size: int, size: int) -> int:
    configmap_dir = output_dir / "configmaps"
    configmap_dir.mkdir(parents=True, exist_ok=True)
    payload = "x" * size
    batch_files = 0
    for start in range(1, count + 1, batch_size):
        end = min(start + batch_size - 1, count)
        documents = [render_configmap(namespaces[(index - 1) % len(namespaces)], index, payload) for index in range(start, end + 1)]
        (configmap_dir / f"batch-{batch_files:03d}.yaml").write_text("---\n".join(documents), encoding="utf-8")
        batch_files += 1
    return batch_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--release", required=True, choices=RELEASES)
    parser.add_argument("--crd-version")
    parser.add_argument("--mode", choices=("passive", "active"), default="passive")
    parser.add_argument("--workloads", type=int, default=25010)
    parser.add_argument("--nodes", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--namespace-count", type=int, default=1000)
    parser.add_argument("--deployments", type=int, default=11500)
    parser.add_argument("--statefulsets", type=int, default=11500)
    parser.add_argument("--cronjobs", type=int, default=2000)
    parser.add_argument("--daemonsets", type=int, default=10)
    parser.add_argument("--configmaps", type=int, default=10000)
    parser.add_argument("--configmap-size", type=int, default=4096)
    parser.add_argument("--cluster-name", default="memory-release-benchmark")
    parser.add_argument("--kubex-host", default="automationtest.kubex.ai")
    parser.add_argument("--kubex-cluster-name", default="automation-memory-benchmark")
    parser.add_argument("--release-name", default="kubex-automation-engine")
    parser.add_argument("--release-namespace", default="kubex")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.mode == "active" and not compaction_supported(args.release):
        raise ValueError(f"active compaction is unavailable in {args.release}")
    if args.workloads < 4:
        raise ValueError("--workloads must be at least 4")
    if args.configmaps < 0 or args.configmap_size < 0:
        raise ValueError("ConfigMap count and size must not be negative")
    if sum((args.deployments, args.statefulsets, args.cronjobs, args.daemonsets)) != args.workloads:
        raise ValueError("workload kind counts must sum to --workloads")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    namespaces = [f"perf-{index:04d}" for index in range(1, args.namespace_count + 1)]
    counts = {
        "Deployment": args.deployments,
        "StatefulSet": args.statefulsets,
        "CronJob": args.cronjobs,
        "DaemonSet": args.daemonsets,
    }
    (output_dir / "install-values.yaml").write_text(
        render_values(args.kubex_host, args.kubex_cluster_name, args.release, args.mode), encoding="utf-8"
    )
    (output_dir / "namespaces.yaml").write_text(
        "---\n".join(build_scenario.render_namespace(name) for name in namespaces), encoding="utf-8"
    )
    (output_dir / "strategy.yaml").write_text(build_scenario.render_strategy("perf-static-strategy"), encoding="utf-8")
    (output_dir / "policy.yaml").write_text(
        build_scenario.render_policy("perf-static-policy", "perf-static-strategy", namespaces), encoding="utf-8"
    )
    if args.mode == "active":
        (output_dir / "compaction-policy.yaml").write_text(
            render_compaction_policy("perf-compaction", namespaces), encoding="utf-8"
        )
    build_scenario.write_batches(output_dir, namespaces, args.workloads, args.batch_size, counts)
    configmap_batch_files = write_configmap_batches(output_dir, namespaces, args.configmaps, args.batch_size, args.configmap_size)
    metadata = {
        "benchmark": "stable-release-memory",
        "release": args.release,
        "crd_version": args.crd_version or crd_version_for(args.release),
        "mode": args.mode,
        "compaction_supported": compaction_supported(args.release),
        "cluster_name": args.cluster_name,
        "release_name": args.release_name,
        "release_namespace": args.release_namespace,
        "workloads": args.workloads,
        "nodes": args.nodes,
        "namespace_count": len(namespaces),
        "batch_size": args.batch_size,
        "batch_files": (args.workloads + args.batch_size - 1) // args.batch_size,
        "configmaps": args.configmaps,
        "configmap_size_bytes": args.configmap_size,
        "configmap_batch_files": configmap_batch_files,
        "workload_kind_counts": counts,
        "controller_install_order": "before-workload-ramp",
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
