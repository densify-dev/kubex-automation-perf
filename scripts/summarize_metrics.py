#!/usr/bin/env python3
"""Summarize the nightly KWOK performance run."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def parse_bytes(value: str) -> float:
    units = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
        "Pi": 1024**5,
        "Ei": 1024**6,
    }
    for unit, multiplier in units.items():
        if value.endswith(unit):
            return float(value[: -len(unit)]) * multiplier
    return float(value)


def parse_cpu(value: str) -> float:
    if value.endswith("n"):
        return float(value[:-1]) / 1_000_000
    if value.endswith("u"):
        return float(value[:-1]) / 1_000
    if value.endswith("m"):
        return float(value[:-1])
    return float(value) * 1000


def scrape_metric(snapshot: str, metric_name: str) -> list[float]:
    pattern = re.compile(rf"^{re.escape(metric_name)}(?:\{{[^}}]*\}})?\s+([0-9.eE+-]+)$", re.MULTILINE)
    return [float(match) for match in pattern.findall(snapshot)]


def latest_snapshot(files: list[Path]) -> Path | None:
    return sorted(files)[-1] if files else None


def read_counts(counts_path: Path) -> tuple[dict[str, int], list[str]]:
    counts: dict[str, int] = {}
    unavailable: list[str] = []
    for line in counts_path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        try:
            counts[key.strip()] = int(value.strip())
        except ValueError:
            unavailable.append(key.strip())
    return counts, unavailable


def workload_total(counts: dict[str, int]) -> int:
    return sum(
        counts.get(key, 0)
        for key in ["deployments", "statefulsets", "cronjobs", "daemonsets"]
    )


def parse_top_pod(path: Path) -> dict[str, float] | None:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    rows = [re.split(r"\s+", line) for line in lines[1:]]
    max_cpu_mcores: float | None = None
    max_memory_bytes: float | None = None
    for row in rows:
        if len(row) < 3:
            continue
        try:
            cpu_m = parse_cpu(row[1])
            mem_b = parse_bytes(row[2])
        except ValueError:
            continue
        max_cpu_mcores = cpu_m if max_cpu_mcores is None else max(max_cpu_mcores, cpu_m)
        max_memory_bytes = mem_b if max_memory_bytes is None else max(max_memory_bytes, mem_b)
    if max_cpu_mcores is None or max_memory_bytes is None:
        return None
    return {"cpu_mcores": max_cpu_mcores, "memory_bytes": max_memory_bytes}


def parse_live_count_snapshot(path: Path) -> dict[str, object] | None:
    counts: dict[str, object] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key == "timestamp":
            counts[key] = value
            continue
        try:
            counts[key] = int(value)
        except ValueError:
            continue
    if "timestamp" not in counts or "pods" not in counts:
        return None
    return counts


def parse_scrape_status(path: Path) -> dict[str, str] | None:
    status: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        status[key.strip()] = value.strip()
    return status or None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--metrics-dir", required=True)
    parser.add_argument("--final-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    metadata = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
    metrics_dir = Path(args.metrics_dir)
    final_dir = Path(args.final_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics_files = sorted((metrics_dir / "metrics").glob("*.prom"))
    metrics_status_files = sorted((metrics_dir / "metrics").glob("*.status"))
    top_files = sorted((metrics_dir / "top").glob("top-pod-*.txt"))
    live_count_files = sorted((metrics_dir / "snapshots").glob("live-counts-*.txt"))

    valid_metrics_files = [path for path in metrics_files if path.read_text(encoding="utf-8").strip()]
    latest_metrics = valid_metrics_files[-1].read_text(encoding="utf-8") if valid_metrics_files else ""
    empty_metrics_files = [path for path in metrics_files if not path.read_text(encoding="utf-8").strip()]
    scrape_statuses = [parse_scrape_status(path) for path in metrics_status_files]
    scrape_statuses = [status for status in scrape_statuses if status]
    scrape_empty_count = sum(1 for status in scrape_statuses if status.get("status") == "empty")
    scrape_error_count = sum(1 for status in scrape_statuses if status.get("status") == "error")
    scrape_recovered_count = sum(1 for status in scrape_statuses if status.get("status") == "success" and status.get("bytes") not in {None, "0"})
    gauge_candidates = defaultdict(float)
    for name in [
        "process_resident_memory_bytes",
        "process_cpu_seconds_total",
        "go_goroutines",
        "workqueue_depth",
        "controller_runtime_reconcile_total",
        "controller_runtime_reconcile_errors_total",
    ]:
        values = scrape_metric(latest_metrics, name)
        if not values:
            continue
        gauge_candidates[name] = max(values) if name in {"workqueue_depth"} else sum(values)

    top_cpu: float | None = None
    top_memory: float | None = None
    valid_top_samples = 0
    for path in top_files:
        sample = parse_top_pod(path)
        if not sample:
            continue
        valid_top_samples += 1
        top_cpu = sample["cpu_mcores"] if top_cpu is None else max(top_cpu, sample["cpu_mcores"])
        top_memory = sample["memory_bytes"] if top_memory is None else max(top_memory, sample["memory_bytes"])

    counts, unavailable_counts = read_counts(final_dir / "counts.txt") if (final_dir / "counts.txt").exists() else ({}, ["counts_file"])
    live_counts: list[dict[str, int]] = []
    for path in live_count_files:
        sample = parse_live_count_snapshot(path)
        if sample:
            live_counts.append(sample)

    latest_live_pods = live_counts[-1]["pods"] if live_counts else counts.get("pods", 0)
    metrics_capture_issue = None
    if not metrics_files:
        metrics_capture_issue = "no metrics scrapes were captured"
    elif metrics_files and len(empty_metrics_files) == len(metrics_files):
        metrics_capture_issue = f"all {len(metrics_files)} metrics scrapes were empty"
    elif scrape_error_count:
        metrics_capture_issue = f"{scrape_error_count} metrics scrape(s) failed"
    elif scrape_empty_count:
        metrics_capture_issue = f"{scrape_empty_count} metrics scrape(s) returned empty output"
    elif scrape_recovered_count:
        metrics_capture_issue = "ok"

    data_issues = []
    if metrics_capture_issue != "ok":
        data_issues.append(metrics_capture_issue)
    if not valid_top_samples:
        data_issues.append("no valid controller resource samples")
    if unavailable_counts:
        data_issues.append(f"unavailable final counts: {', '.join(unavailable_counts)}")

    max_cpu_mcores = round(top_cpu, 2) if top_cpu is not None else None
    max_memory_mib = round(top_memory / (1024 * 1024), 2) if top_memory is not None else None
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario": metadata,
        "samples": {
            "metrics_snapshots": len(metrics_files),
            "empty_metrics_snapshots": len(empty_metrics_files),
            "valid_metrics_snapshots": len(valid_metrics_files),
            "top_snapshots": len(top_files),
            "valid_top_snapshots": valid_top_samples,
            "live_count_snapshots": len(live_counts),
        },
        "counts": counts,
        "live_counts": live_counts,
        "controller": {
            "max_cpu_mcores": max_cpu_mcores,
            "max_memory_mib": max_memory_mib,
        },
        "data_status": "valid" if not data_issues else "degraded",
        "data_issues": data_issues,
        "metrics": gauge_candidates,
        "artifacts": {
            "metrics_dir": str(metrics_dir),
            "final_dir": str(final_dir),
        },
    }

    kind_counts = metadata.get("workload_kind_counts", {})
    daemonset_count = counts.get("daemonsets", 0)
    deployment_count = counts.get("deployments", 0)
    statefulset_count = counts.get("statefulsets", 0)
    cronjob_count = counts.get("cronjobs", 0)
    pod_bearing_objects = deployment_count + statefulset_count + cronjob_count + daemonset_count
    daemonset_pod_target = daemonset_count * int(metadata.get("nodes", 0))
    expected_steady_state_pods = deployment_count + statefulset_count + daemonset_pod_target
    pod_delta = counts.get("pods", 0) - expected_steady_state_pods

    key_metrics = {
        "controller_max_cpu_mcores": max_cpu_mcores,
        "controller_max_memory_mib": max_memory_mib,
        "workload_objects_observed": workload_total(counts),
        "pod_bearing_workload_objects_observed": pod_bearing_objects,
        "expected_live_pods_from_daemonsets": daemonset_pod_target,
        "expected_steady_state_live_pods": expected_steady_state_pods,
        "final_pods_observed": counts.get("pods", 0),
        "latest_live_pods_observed": latest_live_pods,
        "workload_pods_observed": latest_live_pods,
        "live_pod_delta_vs_target": latest_live_pods - expected_steady_state_pods,
        "empty_metrics_snapshots": len(empty_metrics_files),
        "metrics_capture_issue": metrics_capture_issue or "ok",
        "metrics_snapshots": len(metrics_files),
        "valid_metrics_snapshots": len(valid_metrics_files),
        "top_snapshots": len(top_files),
        "valid_top_snapshots": valid_top_samples,
        "live_count_snapshots": len(live_counts),
    }
    for key in sorted(gauge_candidates):
        key_metrics[key] = gauge_candidates[key]
    summary["key_metrics"] = key_metrics

    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md_lines = [
        "# KWOK Nightly Summary",
        "",
        f"- controller install order: {metadata.get('controller_install_order', 'unknown')}",
        f"- workloads: {metadata['workloads']}",
        f"- nodes: {metadata['nodes']}",
        f"- workload mix: deployments={kind_counts.get('Deployment', 0)}, statefulsets={kind_counts.get('StatefulSet', 0)}, cronjobs={kind_counts.get('CronJob', 0)}, daemonsets={kind_counts.get('DaemonSet', 0)}",
        f"- namespaces: {metadata['namespace_count']}",
        f"- batches: {metadata['batch_files']}",
        f"- metrics snapshots: {len(metrics_files)}",
        f"- empty metrics snapshots: {len(empty_metrics_files)}",
        f"- live count snapshots: {len(live_counts)}",
        f"- valid controller resource snapshots: {valid_top_samples}",
        f"- controller max CPU: {max_cpu_mcores if max_cpu_mcores is not None else 'unavailable'} mcores",
        f"- controller max memory: {max_memory_mib if max_memory_mib is not None else 'unavailable'} MiB",
        f"- workload objects observed: {workload_total(counts)}",
        f"- pod-bearing workload objects observed: {pod_bearing_objects}",
        f"- expected live pods from daemonsets: {daemonset_pod_target}",
        f"- expected steady-state live pods: {expected_steady_state_pods}",
        f"- final pods observed: {counts.get('pods', 0)}",
        f"- latest live pods observed: {latest_live_pods}",
        f"- live pod delta vs target: {latest_live_pods - expected_steady_state_pods}",
        "",
        "CronJobs are active, but they are scheduled workloads rather than a steady-state pod source.",
        "",
        f"Metrics capture status: {metrics_capture_issue or 'ok'}",
        f"Data status: {summary['data_status']}",
        "",
        "## Key metrics",
    ]
    for key, value in key_metrics.items():
        md_lines.append(f"- {key}: {value}")
    md_lines.extend([
        "",
        "## Artifacts",
        f"- metrics: `{metrics_dir}`",
        f"- final state: `{final_dir}`",
    ])
    (output_dir / "summary.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
