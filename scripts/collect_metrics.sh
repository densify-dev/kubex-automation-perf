#!/usr/bin/env bash
set -euo pipefail

namespace="kubex"
release="kubex-automation-engine"
port_forward_port="18080"
output_dir=""
stop_file=""
interval="15"
count_interval="30"
heavy_snapshot_interval="120"
kubectl_timeout="20"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace)
      namespace="$2"
      shift 2
      ;;
    --release)
      release="$2"
      shift 2
      ;;
    --port-forward-port)
      port_forward_port="$2"
      shift 2
      ;;
    --output-dir)
      output_dir="$2"
      shift 2
      ;;
    --stop-file)
      stop_file="$2"
      shift 2
      ;;
    --interval)
      interval="$2"
      shift 2
      ;;
    --count-interval)
      count_interval="$2"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "${output_dir}" || -z "${stop_file}" ]]; then
  echo "--output-dir and --stop-file are required" >&2
  exit 2
fi

mkdir -p "${output_dir}/metrics" "${output_dir}/top" "${output_dir}/snapshots"

service="${release}-metrics-service"
port_forward_log="${output_dir}/port-forward.log"

pf_pid=""

start_port_forward() {
  if [[ -n "${pf_pid}" ]]; then
    kill "${pf_pid}" >/dev/null 2>&1 || true
    wait "${pf_pid}" >/dev/null 2>&1 || true
  fi
  kubectl -n "${namespace}" port-forward "svc/${service}" "${port_forward_port}:8080" >"${port_forward_log}" 2>&1 &
  pf_pid=$!
}

wait_for_port_forward() {
  for _ in $(seq 1 20); do
    if curl -fsS "http://127.0.0.1:${port_forward_port}/metrics" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

scrape_metrics() {
  local metrics_file="$1"
  local metrics_status_file="$2"
  local attempt rc empty_seen="false" failure_seen="false"

  for attempt in 1 2 3 4 5; do
    if curl -fsS --max-time 10 "http://127.0.0.1:${port_forward_port}/metrics" >"${metrics_file}"; then
      if [[ -s "${metrics_file}" ]]; then
        printf 'status=success\nbytes=%s\n' "$(wc -c <"${metrics_file}" | tr -d ' ')" >"${metrics_status_file}"
        return 0
      fi
      empty_seen="true"
    else
      failure_seen="true"
      rc=$?
    fi

    sleep 1

    if [[ ${attempt} -lt 5 ]]; then
      start_port_forward
      wait_for_port_forward || true
    fi
  done

  : >"${metrics_file}"
  if [[ "${empty_seen}" == "true" && "${failure_seen}" != "true" ]]; then
    printf 'status=empty\nreason=empty_response\n' >"${metrics_status_file}"
  else
    printf 'status=error\nreason=curl_failed\nexit_code=%s\n' "${rc:-1}" >"${metrics_status_file}"
  fi
  return 1
}

start_port_forward
wait_for_port_forward || true

cleanup() {
  if [[ -n "${pf_pid}" ]]; then
    kill "${pf_pid}" >/dev/null 2>&1 || true
    wait "${pf_pid}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

run_kubectl() {
  timeout "${kubectl_timeout}" kubectl "$@"
}

write_live_counts() {
  local ts="$1"
  local snapshot="${output_dir}/snapshots/live-counts-${ts}.txt"
  local temporary="${snapshot}.tmp"
  if {
    echo "timestamp=${ts}"
    run_kubectl get deploy -A -l app.kubernetes.io/name=kwok-perf -o name 2>/dev/null | wc -l | tr -d ' ' | xargs printf 'deployments=%s\n'
    run_kubectl get statefulsets -A -l app.kubernetes.io/name=kwok-perf -o name 2>/dev/null | wc -l | tr -d ' ' | xargs printf 'statefulsets=%s\n'
    run_kubectl get cronjobs -A -l app.kubernetes.io/name=kwok-perf -o name 2>/dev/null | wc -l | tr -d ' ' | xargs printf 'cronjobs=%s\n'
    run_kubectl get daemonsets -A -l app.kubernetes.io/name=kwok-perf -o name 2>/dev/null | wc -l | tr -d ' ' | xargs printf 'daemonsets=%s\n'
    run_kubectl get pod -A -l app.kubernetes.io/name=kwok-perf -o name 2>/dev/null | wc -l | tr -d ' ' | xargs printf 'pods=%s\n'
  } >"${temporary}"; then
    mv "${temporary}" "${snapshot}"
  else
    rm -f "${temporary}"
    return 1
  fi
}

next_count_at=$(date +%s)
next_heavy_at=$(date +%s)

while [[ ! -f "${stop_file}" ]]; do
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  metrics_file="${output_dir}/metrics/metrics-${ts}.prom"
  metrics_status_file="${output_dir}/metrics/metrics-${ts}.status"
  scrape_metrics "${metrics_file}" "${metrics_status_file}" || true
  run_kubectl top pod -n "${namespace}" -l control-plane=controller-manager >"${output_dir}/top/top-pod-${ts}.txt" 2>&1 || true
  run_kubectl top node >"${output_dir}/top/top-node-${ts}.txt" 2>&1 || true
  now=$(date +%s)
  if [[ ${now} -ge ${next_count_at} ]]; then
    write_live_counts "${ts}" || true
    next_count_at=$((now + count_interval))
  fi
  if [[ ${now} -ge ${next_heavy_at} ]]; then
    if [[ -z "${heavy_pid:-}" ]] || ! kill -0 "${heavy_pid}" 2>/dev/null; then
      (
        run_kubectl get deploy,statefulsets,cronjobs,daemonsets -A -l app.kubernetes.io/name=kwok-perf >"${output_dir}/snapshots/workloads-${ts}.txt" 2>&1 || true
        run_kubectl get pod -A -l app.kubernetes.io/name=kwok-perf >"${output_dir}/snapshots/pods-${ts}.txt" 2>&1 || true
        run_kubectl get globalconfiguration global-config -o yaml >"${output_dir}/snapshots/globalconfiguration-${ts}.yaml" 2>&1 || true
      ) &
      heavy_pid=$!
      next_heavy_at=$((now + heavy_snapshot_interval))
    fi
  fi
  sleep "${interval}"
done
