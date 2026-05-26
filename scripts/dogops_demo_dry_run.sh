#!/usr/bin/env bash
set -euo pipefail

export UV_CACHE_DIR="${UV_CACHE_DIR:-${TMPDIR:-/tmp}/dogops-uv-cache}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"

RUN_DIR="${RUN_DIR:-.dogops/runs/latest}"
PORT="${PORT:-8765}"
HOST="${HOST:-127.0.0.1}"

cleanup() {
  if [[ -n "${server_pid:-}" ]]; then
    kill "${server_pid}" >/dev/null 2>&1 || true
    wait "${server_pid}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

uv run python -m dimos.experimental.dogops.cli validate \
  --site examples/dogops/site_demo.yaml \
  --manifest examples/dogops/manifest_demo.yaml \
  --mission examples/dogops/mission_demo.yaml

uv run python -m dimos.experimental.dogops.cli simulate \
  --site examples/dogops/site_demo.yaml \
  --manifest examples/dogops/manifest_demo.yaml \
  --mission examples/dogops/mission_demo.yaml \
  --out "${RUN_DIR}"

test -f "${RUN_DIR}/report.md"
rg 'INC-001.*resolved|PKG-103.*missing|Nav:' "${RUN_DIR}/report.md"

uv run python -m dimos.experimental.dogops.cli serve \
  --run "${RUN_DIR}" \
  --host "${HOST}" \
  --port "${PORT}" >/tmp/dogops-demo-server.log 2>&1 &
server_pid="$!"

for _ in {1..50}; do
  if curl -fsS "http://${HOST}:${PORT}/api/state" >/tmp/dogops-demo-state.json 2>/dev/null; then
    break
  fi
  sleep 0.1
done

curl -fsS "http://${HOST}:${PORT}/api/report" >/tmp/dogops-demo-report.json
curl -fsS "http://${HOST}:${PORT}/api/nav" >/tmp/dogops-demo-nav.json

jq -e '.run.state == "done"' /tmp/dogops-demo-state.json >/dev/null
jq -e '.manifest_exceptions == 2' /tmp/dogops-demo-report.json >/dev/null
jq -e '.waypoints_reached == 4 and .route_coverage == 1' /tmp/dogops-demo-nav.json >/dev/null

echo "DogOps dry run passed: ${RUN_DIR} on http://${HOST}:${PORT}"
