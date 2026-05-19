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

kubectl get deploy,statefulsets,cronjobs -A -l app.kubernetes.io/name=kwok-perf -o wide >"${output_dir}/workloads.txt" 2>&1 || true
kubectl get pod -A -l app.kubernetes.io/name=kwok-perf -o wide >"${output_dir}/pods.txt" 2>&1 || true
kubectl get rs -A -l app.kubernetes.io/name=kwok-perf -o wide >"${output_dir}/replicasets.txt" 2>&1 || true
kubectl get deploy,rs,pod -n "${namespace}" -o wide >"${output_dir}/controller-namespace.txt" 2>&1 || true
kubectl get globalconfiguration global-config -o yaml >"${output_dir}/globalconfiguration.yaml" 2>&1 || true
kubectl get clusterautomationstrategies >"${output_dir}/clusterautomationstrategies.txt" 2>&1 || true
kubectl get clusterstaticpolicies >"${output_dir}/clusterstaticpolicies.txt" 2>&1 || true
kubectl get events -A --sort-by=.lastTimestamp >"${output_dir}/events.txt" 2>&1 || true
kubectl logs -n "${namespace}" -l control-plane=controller-manager -c manager --since=60m >"${output_dir}/controller.log" 2>&1 || true

workloads=$(kubectl get deploy,statefulsets,cronjobs,daemonsets -A -l app.kubernetes.io/name=kwok-perf -o name 2>/dev/null | wc -l | tr -d ' ')
deployments=$(kubectl get deploy -A -l app.kubernetes.io/name=kwok-perf -o name 2>/dev/null | wc -l | tr -d ' ')
statefulsets=$(kubectl get statefulsets -A -l app.kubernetes.io/name=kwok-perf -o name 2>/dev/null | wc -l | tr -d ' ')
cronjobs=$(kubectl get cronjobs -A -l app.kubernetes.io/name=kwok-perf -o name 2>/dev/null | wc -l | tr -d ' ')
daemonsets=$(kubectl get daemonsets -A -l app.kubernetes.io/name=kwok-perf -o name 2>/dev/null | wc -l | tr -d ' ')
pods=$(kubectl get pod -A -l app.kubernetes.io/name=kwok-perf -o name 2>/dev/null | wc -l | tr -d ' ')
replicasets=$(kubectl get rs -A -l app.kubernetes.io/name=kwok-perf -o name 2>/dev/null | wc -l | tr -d ' ')
controller_pods=$(kubectl get pod -n "${namespace}" -l control-plane=controller-manager -o name 2>/dev/null | wc -l | tr -d ' ')

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
