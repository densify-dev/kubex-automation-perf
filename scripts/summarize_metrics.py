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


def read_counts(counts_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in counts_path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        counts[key.strip()] = int(value.strip())
    return counts


def parse_top_pod(path: Path) -> dict[str, float] | None:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    rows = [re.split(r"\s+", line) for line in lines[1:]]
    best: dict[str, float] | None = None
    for row in rows:
        if len(row) < 3:
            continue
        try:
            cpu_m = parse_cpu(row[1])
            mem_b = parse_bytes(row[2])
        except ValueError:
            continue
        candidate = {"cpu_mcores": cpu_m, "memory_bytes": mem_b}
        if best is None or cpu_m > best["cpu_mcores"]:
            best = candidate
    return best


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
    top_files = sorted((metrics_dir / "top").glob("top-pod-*.txt"))

    latest_metrics = metrics_files[-1].read_text(encoding="utf-8") if metrics_files else ""
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

    top_cpu = 0.0
    top_memory = 0.0
    for path in top_files:
        sample = parse_top_pod(path)
        if not sample:
            continue
        top_cpu = max(top_cpu, sample["cpu_mcores"])
        top_memory = max(top_memory, sample["memory_bytes"])

    counts = read_counts(final_dir / "counts.txt") if (final_dir / "counts.txt").exists() else {}

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario": metadata,
        "samples": {
            "metrics_snapshots": len(metrics_files),
            "top_snapshots": len(top_files),
        },
        "counts": counts,
        "controller": {
            "max_cpu_mcores": round(top_cpu, 2),
            "max_memory_mib": round(top_memory / (1024 * 1024), 2),
        },
        "metrics": gauge_candidates,
        "artifacts": {
            "metrics_dir": str(metrics_dir),
            "final_dir": str(final_dir),
        },
    }

    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md_lines = [
        "# KWOK Nightly Summary",
        "",
        f"- workloads: {metadata['workloads']}",
        f"- namespaces: {metadata['namespace_count']}",
        f"- batches: {metadata['batch_files']}",
        f"- metrics snapshots: {len(metrics_files)}",
        f"- controller max CPU: {round(top_cpu, 2)} mcores",
        f"- controller max memory: {round(top_memory / (1024 * 1024), 2)} MiB",
        f"- workload deployments observed: {counts.get('deployments', 0)}",
        f"- workload pods observed: {counts.get('pods', 0)}",
        "",
        "## Key metrics",
    ]
    for key in sorted(gauge_candidates):
        md_lines.append(f"- {key}: {gauge_candidates[key]}")
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
