# Kubex Automation KWOK Perf Harness

Nightly GitHub Action for exercising `kubex-automation-engine` at scale on KWOK.

## What it runs

- creates a KWOK cluster with metrics-server enabled
- scales KWOK nodes to the requested size before controller install
- installs `kubex-crds`
- applies a mixed workload set before the controller starts
- installs `kubex-automation-engine` with the gateway disabled and fetch suppression enabled
- applies a cluster-wide `StaticPolicy`
- creates 10k synthetic workloads by default across `Deployment`, `StatefulSet`, and `CronJob`
- scrapes controller metrics during the run
- prints live workload and controller health progress while waiting
- uploads raw data and a run summary as artifacts

Note: the chart still mounts the gateway secret volume even when the gateway container is disabled, so the workflow creates a placeholder `kubex-gateway-config` Secret.

## Where metrics are stored

Each run writes:

- `artifacts/metrics/` for raw `/metrics` snapshots and `kubectl top` samples
- `artifacts/final/` for end-of-run object state, events, and logs
- `artifacts/report/summary.json` and `summary.md` for the human-readable result
- `gh-pages` branch for persistent run history and a simple dashboard

The dashboard includes basic CPU and memory trend charts, a recent-runs table, and a CSV export.

The workflow also appends the Markdown summary to the GitHub Actions job summary, so the latest run is visible without downloading artifacts.

## Nightly workflow

Workflow file: `.github/workflows/performance-daily.yml`

The workflow runs twice per execution via a matrix:

- controller installed before workload ramp
- controller installed after workload ramp

The workflow is manually runnable too, with inputs for:

- workload count
- KWOK node count
- chart version

## Local script entry points

- `scripts/build_scenario.py`
- `scripts/kwok_orchestrate.py`
- `scripts/collect_metrics.sh`
- `scripts/collect_final_state.sh`
- `scripts/summarize_metrics.py`

## Notes

- The harness is intentionally StaticPolicy-only for the first cut.
- Long-term trend storage is published to the `gh-pages` branch after each nightly run.

## Stable release memory benchmark

Workflow: `.github/workflows/memory-release-benchmark.yml`

The manual release sweep compares `1.8.0`, `1.9.0`, `1.9.1`, `1.10.0`,
`1.11.0`, `1.11.1`, and `1.11.2` using the same KWOK workload profile. Passive
scenarios run for every release. Active compaction scenarios run for `1.10.0`
and later, where the CRD exists.

The comparison uses manager-process RSS after a completed Go GC. An adjacent
release is flagged when memory increases by at least 20% and 50 MiB. Reports
include the raw time series, post-GC summaries, and an adjacent-release table.

Generate a small local scenario with:

```bash
python3 scripts/build_memory_scenario.py \
  --output-dir /tmp/memory-scenario \
  --release 1.10.0 \
  --mode active \
  --workloads 4 \
  --nodes 2 \
  --namespace-count 1 \
  --deployments 1 \
  --statefulsets 1 \
  --cronjobs 1 \
  --daemonsets 1
```
