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

kubectl get deploy -A -l app.kubernetes.io/name=kwok-perf -o wide >"${output_dir}/deployments.txt" 2>&1 || true
kubectl get pod -A -l app.kubernetes.io/name=kwok-perf -o wide >"${output_dir}/pods.txt" 2>&1 || true
kubectl get globalconfiguration global-config -o yaml >"${output_dir}/globalconfiguration.yaml" 2>&1 || true
kubectl get clusterautomationstrategies >"${output_dir}/clusterautomationstrategies.txt" 2>&1 || true
kubectl get clusterstaticpolicies >"${output_dir}/clusterstaticpolicies.txt" 2>&1 || true
kubectl get events -A --sort-by=.lastTimestamp >"${output_dir}/events.txt" 2>&1 || true
kubectl logs -n "${namespace}" -l control-plane=controller-manager -c manager --since=60m >"${output_dir}/controller.log" 2>&1 || true

deployments=$(kubectl get deploy -A -l app.kubernetes.io/name=kwok-perf -o name 2>/dev/null | wc -l | tr -d ' ')
pods=$(kubectl get pod -A -l app.kubernetes.io/name=kwok-perf -o name 2>/dev/null | wc -l | tr -d ' ')
controller_pods=$(kubectl get pod -n "${namespace}" -l control-plane=controller-manager -o name 2>/dev/null | wc -l | tr -d ' ')

cat >"${output_dir}/counts.txt" <<EOF
deployments=${deployments}
pods=${pods}
controller_pods=${controller_pods}
EOF
