#!/usr/bin/env bash
set -euo pipefail

export UV_CACHE_DIR="${UV_CACHE_DIR:-${TMPDIR:-/tmp}/dogops-uv-cache}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"

RUN_DIR="${RUN_DIR:-.dogops/runs/latest}"
PORT="${PORT:-8765}"
HOST="${HOST:-127.0.0.1}"
if [[ -n "${UV_RUN_ARGS:-}" ]]; then
  read -r -a uv_run_args <<< "${UV_RUN_ARGS}"
else
  uv_run_args=(--no-sync)
fi

uv_run() {
  uv run "${uv_run_args[@]}" "$@"
}

cleanup() {
  if [[ -n "${server_pid:-}" ]]; then
    kill "${server_pid}" >/dev/null 2>&1 || true
    wait "${server_pid}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

uv_run python -m dimos.experimental.dogops.cli validate \
  --site examples/dogops/site_demo.yaml \
  --manifest examples/dogops/manifest_demo.yaml \
  --mission examples/dogops/mission_demo.yaml

uv_run python -m dimos.experimental.dogops.cli simulate \
  --site examples/dogops/site_demo.yaml \
  --manifest examples/dogops/manifest_demo.yaml \
  --mission examples/dogops/mission_demo.yaml \
  --out "${RUN_DIR}"

test -f "${RUN_DIR}/report.md"
rg 'INC-001.*resolved|PKG-103.*missing|Nav:' "${RUN_DIR}/report.md"

uv_run python -m dimos.experimental.dogops.cli serve \
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
curl -fsS "http://${HOST}:${PORT}/api/map" >/tmp/dogops-demo-map.json
curl -fsS "http://${HOST}:${PORT}/api/route" >/tmp/dogops-demo-route.json
curl -fsS "http://${HOST}:${PORT}/api/poi" >/tmp/dogops-demo-poi.json

jq -e '.run.state == "done"' /tmp/dogops-demo-state.json >/dev/null
jq -e '.manifest_exceptions == 2' /tmp/dogops-demo-report.json >/dev/null
jq -e '.checkpoints_verified == 4 and .checkpoints_total == 4' /tmp/dogops-demo-report.json >/dev/null
jq -e '.waypoints_reached == 4 and .route_coverage == 1' /tmp/dogops-demo-nav.json >/dev/null
jq -e '.route | map(.target_id) == ["HOME","INBOUND_DOCK","COOLING_1","QA_HOLD"]' \
  /tmp/dogops-demo-map.json >/dev/null
jq -e '.stops | map(.target_id) == ["HOME","INBOUND_DOCK","COOLING_1","QA_HOLD"]' \
  /tmp/dogops-demo-route.json >/dev/null
jq -e 'any(.captures[]; .id == "OBS-003") and any(.readings[]; .asset_id == "TEMP_1")' \
  /tmp/dogops-demo-poi.json >/dev/null

echo "DogOps dry run passed: ${RUN_DIR} on http://${HOST}:${PORT}"
