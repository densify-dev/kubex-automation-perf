#!/usr/bin/env bash
set -euo pipefail

namespace="kubex"
release="kubex-automation-engine"
port_forward_port="18080"
output_dir=""
stop_file=""
interval="15"
count_interval="60"

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

kubectl -n "${namespace}" port-forward "svc/${service}" "${port_forward_port}:8080" >"${port_forward_log}" 2>&1 &
pf_pid=$!

cleanup() {
  kill "${pf_pid}" >/dev/null 2>&1 || true
  wait "${pf_pid}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

write_live_counts() {
  ts="$1"
  {
    echo "timestamp=${ts}"
    kubectl get deploy -A -l app.kubernetes.io/name=kwok-perf -o name 2>/dev/null | wc -l | tr -d ' ' | xargs printf 'deployments=%s\n'
    kubectl get statefulsets -A -l app.kubernetes.io/name=kwok-perf -o name 2>/dev/null | wc -l | tr -d ' ' | xargs printf 'statefulsets=%s\n'
    kubectl get cronjobs -A -l app.kubernetes.io/name=kwok-perf -o name 2>/dev/null | wc -l | tr -d ' ' | xargs printf 'cronjobs=%s\n'
    kubectl get daemonsets -A -l app.kubernetes.io/name=kwok-perf -o name 2>/dev/null | wc -l | tr -d ' ' | xargs printf 'daemonsets=%s\n'
    kubectl get pod -A -l app.kubernetes.io/name=kwok-perf -o name 2>/dev/null | wc -l | tr -d ' ' | xargs printf 'pods=%s\n'
  } >"${output_dir}/snapshots/live-counts-${ts}.txt"
}

next_count_at=$(date +%s)

while [[ ! -f "${stop_file}" ]]; do
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  metrics_file="${output_dir}/metrics/metrics-${ts}.prom"
  metrics_status_file="${output_dir}/metrics/metrics-${ts}.status"
  if curl -fsS "http://127.0.0.1:${port_forward_port}/metrics" >"${metrics_file}"; then
    if [[ -s "${metrics_file}" ]]; then
      printf 'status=success\nbytes=%s\n' "$(wc -c <"${metrics_file}" | tr -d ' ')" >"${metrics_status_file}"
    else
      printf 'status=empty\nreason=empty_response\n' >"${metrics_status_file}"
    fi
  else
    rc=$?
    : >"${metrics_file}"
    printf 'status=error\nreason=curl_failed\nexit_code=%s\n' "${rc}" >"${metrics_status_file}"
  fi
  kubectl top pod -n "${namespace}" -l control-plane=controller-manager >"${output_dir}/top/top-pod-${ts}.txt" 2>&1 || true
  kubectl top node >"${output_dir}/top/top-node-${ts}.txt" 2>&1 || true
  kubectl get deploy,statefulsets,cronjobs,daemonsets -A -l app.kubernetes.io/name=kwok-perf >"${output_dir}/snapshots/workloads-${ts}.txt" 2>&1 || true
  kubectl get pod -A -l app.kubernetes.io/name=kwok-perf >"${output_dir}/snapshots/pods-${ts}.txt" 2>&1 || true
  kubectl get globalconfiguration global-config -o yaml >"${output_dir}/snapshots/globalconfiguration-${ts}.yaml" 2>&1 || true
  now=$(date +%s)
  if [[ ${now} -ge ${next_count_at} ]]; then
    write_live_counts "${ts}"
    next_count_at=$((now + count_interval))
  fi
  sleep "${interval}"
done
