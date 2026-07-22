#!/usr/bin/env bash
set -euo pipefail

namespace="kubex"
release="kubex-automation-engine"
output_dir=""

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
    --output-dir)
      output_dir="$2"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "${output_dir}" ]]; then
  echo "--output-dir is required" >&2
  exit 2
fi

mkdir -p "${output_dir}"

timeout 30s kubectl get deploy,statefulsets,cronjobs -A -l app.kubernetes.io/name=kwok-perf -o wide >"${output_dir}/workloads.txt" 2>&1 || true
timeout 30s kubectl get pod -A -l app.kubernetes.io/name=kwok-perf -o wide >"${output_dir}/pods.txt" 2>&1 || true
timeout 30s kubectl get rs -A -l app.kubernetes.io/name=kwok-perf -o wide >"${output_dir}/replicasets.txt" 2>&1 || true
timeout 30s kubectl get deploy,rs,pod -n "${namespace}" -o wide >"${output_dir}/controller-namespace.txt" 2>&1 || true
timeout 30s kubectl get globalconfiguration global-config -o yaml >"${output_dir}/globalconfiguration.yaml" 2>&1 || true
timeout 30s kubectl get clusterautomationstrategies >"${output_dir}/clusterautomationstrategies.txt" 2>&1 || true
timeout 30s kubectl get clusterstaticpolicies >"${output_dir}/clusterstaticpolicies.txt" 2>&1 || true
timeout 1m kubectl get events -n "${namespace}" --sort-by=.lastTimestamp >"${output_dir}/events.txt" 2>&1 || true
timeout 1m kubectl logs -n "${namespace}" -l control-plane=controller-manager -c manager --since=15m --tail=500 >"${output_dir}/controller.log" 2>&1 || true

count_resources() {
  local output
  if ! output=$(timeout 30s kubectl get "$@" -o name 2>/dev/null); then
    printf 'unavailable\n'
  elif [[ -z "${output}" ]]; then
    printf '0\n'
  else
    wc -l <<<"${output}" | tr -d ' '
  fi
}

workloads=$(count_resources deploy,statefulsets,cronjobs,daemonsets -A -l app.kubernetes.io/name=kwok-perf)
deployments=$(count_resources deploy -A -l app.kubernetes.io/name=kwok-perf)
statefulsets=$(count_resources statefulsets -A -l app.kubernetes.io/name=kwok-perf)
cronjobs=$(count_resources cronjobs -A -l app.kubernetes.io/name=kwok-perf)
daemonsets=$(count_resources daemonsets -A -l app.kubernetes.io/name=kwok-perf)
pods=$(count_resources pod -A -l app.kubernetes.io/name=kwok-perf)
replicasets=$(count_resources rs -A -l app.kubernetes.io/name=kwok-perf)
controller_pods=$(count_resources pod -n "${namespace}" -l control-plane=controller-manager)

cat >"${output_dir}/counts.txt" <<EOF
workloads=${workloads}
deployments=${deployments}
statefulsets=${statefulsets}
cronjobs=${cronjobs}
daemonsets=${daemonsets}
pods=${pods}
replicasets=${replicasets}
controller_pods=${controller_pods}
EOF
