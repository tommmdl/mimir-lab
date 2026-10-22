#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
case ${1:-} in
  mimir) service=mimir; ports=8025:9009 ;;
  grafana) service=grafana; ports=8026:3000 ;;
  prometheus) service=prometheus-a; ports=8027:9090 ;;
  *) echo 'Usage: bash scripts/access.sh mimir|grafana|prometheus' >&2; exit 2 ;;
esac
exec bash scripts/k.sh -n mimir-lab port-forward --address 127.0.0.1 "service/$service" "$ports"
