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

Workflow file: `.github/workflows/kwok-nightly.yml`

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
