#!/usr/bin/env bash
set -euo pipefail

resource=""
selector=""
expected=""
timeout="1800"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --resource)
      resource="$2"
      shift 2
      ;;
    --selector)
      selector="$2"
      shift 2
      ;;
    --expected)
      expected="$2"
      shift 2
      ;;
    --timeout)
      timeout="$2"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "${resource}" || -z "${selector}" || -z "${expected}" ]]; then
  echo "--resource, --selector, and --expected are required" >&2
  exit 2
fi

timeout_seconds="${timeout}"
case "${timeout}" in
  *s)
    timeout_seconds="${timeout%s}"
    ;;
  *m)
    timeout_seconds=$(( ${timeout%m} * 60 ))
    ;;
  *h)
    timeout_seconds=$(( ${timeout%h} * 3600 ))
    ;;
esac

deadline=$((SECONDS + timeout_seconds))
while (( SECONDS < deadline )); do
  count=$(kubectl get "${resource}" -A -l "${selector}" -o name 2>/dev/null | wc -l | tr -d ' ')
  if [[ "${count}" == "${expected}" ]]; then
    exit 0
  fi
  sleep 5
done

echo "timed out waiting for ${resource} count ${expected}, last count=${count}" >&2
exit 1
