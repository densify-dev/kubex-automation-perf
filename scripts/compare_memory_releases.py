#!/usr/bin/env python3
"""Compare adjacent release benchmark summaries."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


RELEASE_ORDER = ("1.8.0", "1.9.0", "1.9.1", "1.10.0", "1.11.0", "1.11.1", "1.11.2")


def compare(summaries: list[dict], minimum_mib: float = 50.0, minimum_percent: float = 20.0) -> list[dict]:
    valid = {
        (item.get("mode"), item.get("release")): item
        for item in summaries
        if item.get("status") == "valid"
        and (item.get("manager") or {}).get("post_gc_memory_bytes") is not None
    }
    modes = sorted({item.get("mode") for item in summaries})
    results = []
    for mode in modes:
        releases = [release for release in RELEASE_ORDER if (mode, release) in valid]
        for previous, current in zip(releases, releases[1:]):
            old = valid[(mode, previous)]["manager"]["post_gc_memory_bytes"]
            new = valid[(mode, current)]["manager"]["post_gc_memory_bytes"]
            delta = new - old
            percent = delta / old * 100 if old else None
            flagged = bool(percent is not None and delta >= minimum_mib * 1024**2 and percent >= minimum_percent)
            results.append({"mode": mode, "previous_release": previous, "current_release": current,
                            "previous_post_gc_mib": old / 1024**2, "current_post_gc_mib": new / 1024**2,
                            "delta_mib": delta / 1024**2, "increase_percent": percent,
                            "status": "flagged" if flagged else "within_threshold", "flagged": flagged})
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--minimum-mib", type=float, default=50.0)
    parser.add_argument("--minimum-percent", type=float, default=20.0)
    args = parser.parse_args()
    input_dir = Path(args.input_dir)
    summaries = [json.loads(path.read_text(encoding="utf-8")) for path in input_dir.glob("**/memory-summary.json")]
    results = compare(summaries, args.minimum_mib, args.minimum_percent)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "release-memory.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    with (output_dir / "release-memory.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["mode", "previous_release", "current_release", "previous_post_gc_mib", "current_post_gc_mib", "delta_mib", "increase_percent", "status", "flagged"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)
    lines = ["# Release Memory Comparison", "", "| Mode | Previous | Current | Delta (MiB) | Increase | Status |", "|---|---|---|---:|---:|---|"]
    for result in results:
        lines.append(f"| {result['mode']} | {result['previous_release']} | {result['current_release']} | {result['delta_mib']:.2f} | {result['increase_percent']:.2f}% | {result['status']} |")
    (output_dir / "release-memory.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if any(result["flagged"] for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
