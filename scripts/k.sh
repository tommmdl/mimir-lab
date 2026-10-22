#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
upstream=${KUBERNETES_LAB_DIR:-"$root/../kubernetes-lab"}
exec "$upstream/.local/bin/kubectl" --kubeconfig "$root/.local/kubeconfig" --context kind-devops-sre "$@"
