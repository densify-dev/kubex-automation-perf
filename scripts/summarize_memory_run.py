#!/usr/bin/env python3
"""Summarize manager RSS and Go heap metrics over a benchmark phase."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
import re


METRICS = {
    "rss_bytes": "process_resident_memory_bytes",
    "heap_alloc_bytes": "go_memstats_heap_alloc_bytes",
    "heap_inuse_bytes": "go_memstats_heap_inuse_bytes",
    "heap_sys_bytes": "go_memstats_heap_sys_bytes",
    "heap_idle_bytes": "go_memstats_heap_idle_bytes",
    "heap_released_bytes": "go_memstats_heap_released_bytes",
    "go_memstats_sys_bytes": "go_memstats_sys_bytes",
    "gc_marker": "go_memstats_last_gc_time_seconds",
}
TIMESTAMP_RE = re.compile(r"metrics-(\d{8}T\d{6}Z)\.prom$")
SAMPLE_RE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{[^}]*\})?\s+([0-9.eE+-]+)(?:\s+\d+)?$")


def parse_timestamp(path: Path) -> datetime | None:
    match = TIMESTAMP_RE.search(path.name)
    return datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ") if match else None


def parse_metrics(text: str) -> dict[str, float]:
    result: dict[str, list[float]] = {}
    for line in text.splitlines():
        match = SAMPLE_RE.match(line.strip())
        if not match or match.group(1).startswith("#"):
            continue
        name, value = match.groups()
        try:
            result.setdefault(name, []).append(float(value))
        except ValueError:
            continue
    return {name: sum(values) for name, values in result.items()}


def phase_time(metrics_dir: Path, name: str) -> datetime | None:
    path = metrics_dir / "phases" / f"{name}.timestamp"
    if not path.exists():
        return None
    return datetime.fromisoformat(path.read_text(encoding="utf-8").strip().replace("Z", "+00:00")).replace(tzinfo=None)


def summarize(metrics_dir: Path, metadata: dict) -> dict:
    start = phase_time(metrics_dir, "soak-start")
    end = phase_time(metrics_dir, "soak-end")
    rows: list[dict[str, object]] = []
    for path in sorted((metrics_dir / "metrics").glob("metrics-*.prom")):
        timestamp = parse_timestamp(path)
        if timestamp is None or (start and timestamp < start) or (end and timestamp > end):
            continue
        values = parse_metrics(path.read_text(encoding="utf-8"))
        row: dict[str, object] = {"timestamp": timestamp.isoformat() + "Z", "phase": "soak"}
        for field, metric in METRICS.items():
            row[field] = values.get(metric)
        rows.append(row)

    gc_indices: list[int] = []
    previous = None
    for index, row in enumerate(rows):
        value = row["gc_marker"]
        if not isinstance(value, float):
            continue
        if previous is not None and value > previous:
            gc_indices.append(index)
        previous = value
    rss_rows = [row for row in rows if isinstance(row["rss_bytes"], float)]
    post_gc = []
    for gc_index in gc_indices:
        for row in rows[gc_index:]:
            if isinstance(row["rss_bytes"], float):
                post_gc.append(row["rss_bytes"])
                break
    issues = []
    if len(rss_rows) < 3:
        issues.append("fewer than three RSS samples in soak window")
    if not post_gc:
        issues.append("no completed GC followed by an RSS sample")
    rss = [row["rss_bytes"] for row in rss_rows]
    manager = {
        "post_gc_memory_bytes": statistics.median(post_gc[-3:]) if post_gc else None,
        "post_gc_memory_mib": statistics.median(post_gc[-3:]) / 1024**2 if post_gc else None,
        "post_gc_samples": len(post_gc),
        "steady_rss_median_bytes": statistics.median(rss) if rss else None,
        "steady_rss_p95_bytes": sorted(rss)[max(0, int(len(rss) * 0.95) - 1)] if rss else None,
        "steady_rss_max_bytes": max(rss) if rss else None,
    }
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release": metadata.get("release"),
        "crd_version": metadata.get("crd_version"),
        "mode": metadata.get("mode"),
        "status": "valid" if not issues else "invalid",
        "manager": manager,
        "gc": {"detector_metric": "go_memstats_last_gc_time_seconds", "completed_gc_count_observed": len(gc_indices)},
        "samples": {"soak_rss_samples": len(rss_rows), "soak_metric_samples": len(rows)},
        "data_issues": issues,
    }, rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--metrics-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    metadata = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary, rows = summarize(Path(args.metrics_dir), metadata)
    (output_dir / "memory-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    with (output_dir / "memory-series.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["timestamp", "phase", *METRICS.keys()]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# Memory Release Benchmark",
        "",
        f"- release: `{summary['release']}`",
        f"- mode: `{summary['mode']}`",
        f"- status: `{summary['status']}`",
        f"- post-GC manager RSS: `{summary['manager']['post_gc_memory_mib']}` MiB",
        f"- post-GC samples: `{summary['manager']['post_gc_samples']}`",
        f"- steady-state RSS samples: `{summary['samples']['soak_rss_samples']}`",
    ]
    if summary["data_issues"]:
        lines.extend(["", "## Data Issues", *[f"- {issue}" for issue in summary["data_issues"]]])
    (output_dir / "memory-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
