#!/usr/bin/env python3
"""Write nightly run data into a gh-pages site."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def render_index() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>KWOK Perf History</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; line-height: 1.4; }
    .grid { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); margin: 1rem 0 1.5rem; }
    .card { border: 1px solid #ddd; border-radius: 8px; padding: 1rem; background: #fff; }
    .card h2 { font-size: 1rem; margin: 0 0 0.75rem; }
    canvas { width: 100%; height: 180px; display: block; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ddd; padding: 0.5rem; text-align: left; vertical-align: top; }
    th { background: #f5f5f5; }
    code { background: #f6f8fa; padding: 0.1rem 0.25rem; border-radius: 4px; }
  </style>
</head>
<body>
  <h1>KWOK Perf History</h1>
  <p>Latest nightly runs for kubex-automation-engine.</p>
  <p><strong>Latest status:</strong> <span id="latest-status">Loading...</span> | <a href="history.csv">Download CSV</a></p>
  <div id="status">Loading...</div>
  <div class="grid" id="charts" hidden>
    <div class="card">
      <h2>Controller CPU (mcores)</h2>
      <canvas id="cpu-chart" width="900" height="240"></canvas>
    </div>
    <div class="card">
      <h2>Controller Memory (MiB)</h2>
      <canvas id="memory-chart" width="900" height="240"></canvas>
    </div>
    <div class="card">
      <h2>Live Pods (latest run)</h2>
      <canvas id="pods-chart" width="900" height="240"></canvas>
    </div>
    <div class="card">
      <h2>Latest key metrics</h2>
      <div id="latest-metrics"></div>
    </div>
  </div>
  <table id="runs" hidden>
    <thead>
      <tr>
        <th>Run</th>
        <th>Mode</th>
        <th>When</th>
        <th>Status</th>
        <th>Workloads</th>
        <th>Controller CPU</th>
        <th>Controller Memory</th>
        <th>Pods</th>
        <th>Metrics</th>
        <th>Key metrics</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>
  <script>
    function drawLineChart(canvas, points, color) {
      const ctx = canvas.getContext('2d');
      const dpr = window.devicePixelRatio || 1;
      const cssWidth = canvas.clientWidth || canvas.width;
      const cssHeight = canvas.clientHeight || canvas.height;
      canvas.width = Math.round(cssWidth * dpr);
      canvas.height = Math.round(cssHeight * dpr);
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, cssWidth, cssHeight);
      ctx.strokeStyle = '#e5e7eb';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(40, 10);
      ctx.lineTo(40, cssHeight - 30);
      ctx.lineTo(cssWidth - 10, cssHeight - 30);
      ctx.stroke();

      if (!points.length) {
        ctx.fillStyle = '#6b7280';
        ctx.fillText('No data yet', 60, 40);
        return;
      }

      const values = points.map((p) => p.value);
      const min = Math.min(...values);
      const max = Math.max(...values);
      const span = max === min ? 1 : max - min;
      const left = 40;
      const top = 10;
      const width = cssWidth - 50;
      const height = cssHeight - 40;
      const step = points.length === 1 ? 0 : width / (points.length - 1);

      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      points.forEach((point, index) => {
        const x = left + index * step;
        const y = top + (1 - (point.value - min) / span) * height;
        if (index === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      });
      ctx.stroke();

      ctx.fillStyle = '#111827';
      ctx.font = '12px system-ui, sans-serif';
      ctx.fillText(String(max.toFixed(2)), 4, top + 10);
      ctx.fillText(String(min.toFixed(2)), 4, top + height);
    }

    function renderKeyMetrics(metrics, limit = Infinity) {
      const entries = Object.entries(metrics || {}).slice(0, limit);
      if (!entries.length) {
        return '<p>No key metrics recorded.</p>';
      }
      return `<ul>${entries.map(([key, value]) => `<li><code>${key}</code>: ${value}</li>`).join('')}</ul>`;
    }

    fetch('history.json')
      .then((r) => r.json())
      .then((runs) => {
        const tbody = document.querySelector('#runs tbody');
        const cpuChart = document.querySelector('#cpu-chart');
        const memoryChart = document.querySelector('#memory-chart');
        const podsChart = document.querySelector('#pods-chart');
        const cpuPoints = [];
        const memoryPoints = [];
        const livePodPoints = [];
        const orderedRuns = [...runs].reverse();
        const latest = runs[0];
        const latestStatus = document.querySelector('#latest-status');
        const latestMetrics = document.querySelector('#latest-metrics');
        latestStatus.textContent = latest ? `${latest.status} (${latest.controller_install_order || 'unknown'}, ${latest.generated_at})` : 'No runs yet';
        latestStatus.style.color = latest && latest.status === 'success' ? '#16a34a' : '#dc2626';
        latestMetrics.innerHTML = renderKeyMetrics(latest && latest.key_metrics);
        for (const run of runs) {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td><a href="${run.run_url}">#${run.run_number}</a></td>
            <td>${run.controller_install_order || ''}</td>
            <td>${run.generated_at}</td>
            <td>${run.status}</td>
            <td>${run.workloads}</td>
            <td>${run.controller_max_cpu_mcores} m</td>
            <td>${run.controller_max_memory_mib} MiB</td>
            <td>${run.pods_observed}</td>
            <td>${run.metrics_snapshots}</td>
            <td>${renderKeyMetrics(run.key_metrics, 4)}</td>`;
          tbody.appendChild(tr);
        }
        for (const run of orderedRuns) {
          cpuPoints.push({ label: run.run_number, value: Number(run.controller_max_cpu_mcores || 0) });
          memoryPoints.push({ label: run.run_number, value: Number(run.controller_max_memory_mib || 0) });
        }
        if (latest && Array.isArray(latest.live_counts)) {
          for (const sample of latest.live_counts) {
            livePodPoints.push({ label: sample.timestamp, value: Number(sample.pods || 0) });
          }
        }
        drawLineChart(cpuChart, cpuPoints, '#2563eb');
        drawLineChart(memoryChart, memoryPoints, '#16a34a');
        drawLineChart(podsChart, livePodPoints, '#7c3aed');
        document.querySelector('#charts').hidden = false;
        document.querySelector('#status').hidden = true;
        document.querySelector('#runs').hidden = false;
      })
      .catch((error) => {
        document.querySelector('#status').textContent = `Failed to load history: ${error}`;
      });
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--pages-dir", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-number", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--ref-name", required=True)
    parser.add_argument("--status", required=True)
    args = parser.parse_args()

    summary = json.loads(Path(args.summary_json).read_text(encoding="utf-8"))
    pages_dir = Path(args.pages_dir)
    pages_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = pages_dir / "runs"
    runs_dir.mkdir(exist_ok=True)

    record = {
        "run_id": int(args.run_id),
        "run_key": f"{args.run_id}:{summary['scenario'].get('controller_install_order', 'unknown')}",
        "run_number": int(args.run_number),
        "run_attempt": int(args.run_attempt),
        "run_url": f"https://github.com/{args.repository}/actions/runs/{args.run_id}",
        "sha": args.sha,
        "ref_name": args.ref_name,
        "status": args.status,
        "generated_at": summary["generated_at"],
        "controller_install_order": summary["scenario"].get("controller_install_order", "unknown"),
        "workloads": summary["scenario"]["workloads"],
        "nodes": summary["scenario"]["nodes"],
        "controller_max_cpu_mcores": summary["controller"]["max_cpu_mcores"],
        "controller_max_memory_mib": summary["controller"]["max_memory_mib"],
        "pods_observed": summary.get("counts", {}).get("pods", 0),
        "deployments_observed": summary.get("counts", {}).get("deployments", 0),
        "metrics_snapshots": summary.get("samples", {}).get("metrics_snapshots", 0),
        "top_snapshots": summary.get("samples", {}).get("top_snapshots", 0),
        "live_counts": summary.get("live_counts", []),
        "metrics": summary.get("metrics", {}),
        "key_metrics": summary.get("key_metrics", {}),
    }

    latest_path = runs_dir / f"{record['run_key']}.json"
    latest_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    history_path = pages_dir / "history.json"
    history: list[dict] = []
    if history_path.exists():
        history = json.loads(history_path.read_text(encoding="utf-8"))
        if not isinstance(history, list):
            history = []

    history = [record] + [entry for entry in history if entry.get("run_key", f"{entry.get('run_id')}:{entry.get('controller_install_order', 'unknown')}") != record["run_key"]]
    history = history[:180]
    history_path.write_text(json.dumps(history, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (pages_dir / "latest.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    csv_lines = [
        "run_id,run_key,run_number,run_attempt,generated_at,status,controller_install_order,workloads,nodes,controller_max_cpu_mcores,controller_max_memory_mib,pods_observed,deployments_observed,metrics_snapshots,top_snapshots",
    ]
    for entry in history:
        csv_lines.append(
            ",".join(
                [
                    str(entry.get("run_id", "")),
                    str(entry.get("run_key", f"{entry.get('run_id', '')}:{entry.get('controller_install_order', 'unknown')}")),
                    str(entry.get("run_number", "")),
                    str(entry.get("run_attempt", "")),
                    str(entry.get("generated_at", "")),
                    str(entry.get("status", "")),
                    str(entry.get("controller_install_order", "")),
                    str(entry.get("workloads", "")),
                    str(entry.get("nodes", "")),
                    str(entry.get("controller_max_cpu_mcores", "")),
                    str(entry.get("controller_max_memory_mib", "")),
                    str(entry.get("pods_observed", "")),
                    str(entry.get("deployments_observed", "")),
                    str(entry.get("metrics_snapshots", "")),
                    str(entry.get("top_snapshots", "")),
                ]
            )
        )
    (pages_dir / "history.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")
    (pages_dir / "index.html").write_text(render_index(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
