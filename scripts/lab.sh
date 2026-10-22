#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
upstream=${KUBERNETES_LAB_DIR:-"$PWD/../kubernetes-lab"}
case ${1:-} in
  up)
    expected=$(python3 -c 'import json;print(json.load(open("config/upstream.json"))["commit"])')
    test "$(git -C "$upstream" rev-parse HEAD)" = "$expected" || { echo 'Review the upstream revision before deploying.' >&2; exit 1; }
    mkdir -p .local
    chmod 700 .local
    if ! "$upstream/.local/bin/kind" get clusters | rg -qx devops-sre; then
      node_image=$(python3 -c 'import json;print(json.load(open("config/upstream.json"))["kind_image"])')
      "$upstream/.local/bin/kind" create cluster --name devops-sre --image "$node_image" --config cluster/kind.yaml --kubeconfig "$PWD/.local/kubeconfig" --wait 5m
    fi
    test -f .local/kubeconfig || "$upstream/.local/bin/kind" export kubeconfig --name devops-sre --kubeconfig "$PWD/.local/kubeconfig"
    python3 - <<'PY'
from pathlib import Path
import secrets
for name in ('db-password','grafana-password'):
 p=Path('.local')/name
 if not p.exists():p.write_text(secrets.token_urlsafe(32))
 p.chmod(0o600)
PY
    bash scripts/k.sh apply -f "$upstream/manifests/namespace.yaml"
    bash scripts/k.sh -n notes-lab create secret generic notes-db --from-file=password=.local/db-password --dry-run=client -o yaml | bash scripts/k.sh apply -f -
    bash scripts/k.sh apply -f "$upstream/manifests/config.yaml" -f "$upstream/manifests/postgres.yaml"
    bash scripts/k.sh -n notes-lab rollout status statefulset/postgres-alpine --timeout=240s
    bash scripts/k.sh apply -f "$upstream/manifests/api.yaml"
    bash scripts/k.sh -n notes-lab rollout status deployment/notes-api --timeout=240s
    bash scripts/k.sh create namespace mimir-lab --dry-run=client -o yaml | bash scripts/k.sh apply -f -
    bash scripts/k.sh -n mimir-lab create secret generic grafana-admin --from-file=password=.local/grafana-password --dry-run=client -o yaml | bash scripts/k.sh apply -f -
    bash scripts/k.sh apply -k .
    for deploy in mimir prometheus-a prometheus-b blackbox grafana; do
      bash scripts/k.sh -n mimir-lab rollout status "deployment/$deploy" --timeout=240s
    done
    ;;
  stop) docker stop --timeout 60 devops-sre-control-plane ;;
  start) docker start devops-sre-control-plane ;;
  status) bash scripts/k.sh get pods -A ;;
  *) echo 'Usage: bash scripts/lab.sh up|stop|start|status' >&2; exit 2 ;;
esac
