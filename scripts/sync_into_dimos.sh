#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage:
  scripts/sync_into_dimos.sh /path/to/full/dimos
  DIMOS_ROOT=/path/to/full/dimos scripts/sync_into_dimos.sh

Copies DogOps-owned code and demo config into a full DimOS checkout so the
DimOS blueprint registry and MCP checks can run there.

Set DOGOPS_SYNC_ALLOW_DIRTY=1 to overwrite dirty DogOps-managed target paths.
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
dimos_root="${1:-${DIMOS_ROOT:-}}"

if [[ -z "${dimos_root}" ]]; then
  usage
  exit 2
fi

dimos_root="$(cd "${dimos_root}" && pwd)"

if [[ "${dimos_root}" == "${repo_root}" ]]; then
  echo "Refusing to sync into this DogOps pack; target must be a full DimOS checkout." >&2
  exit 2
fi

required_paths=(
  "pyproject.toml"
  "dimos/core/module.py"
  "dimos/robot/cli/dimos.py"
  "dimos/robot/test_all_blueprints_generation.py"
)

for rel in "${required_paths[@]}"; do
  if [[ ! -e "${dimos_root}/${rel}" ]]; then
    echo "Target does not look like a full DimOS checkout: missing ${rel}" >&2
    exit 2
  fi
done

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required for guarded DogOps sync." >&2
  exit 2
fi

managed_paths=(
  "dimos/experimental/dogops"
  "dimos/robot/unitree/go2/blueprints/agentic/unitree_go2_dogops.py"
  "examples/dogops"
)

if git -C "${dimos_root}" rev-parse --show-toplevel >/dev/null 2>&1; then
  dirty="$(git -C "${dimos_root}" status --porcelain -- "${managed_paths[@]}" || true)"
  if [[ -n "${dirty}" && "${DOGOPS_SYNC_ALLOW_DIRTY:-0}" != "1" ]]; then
    echo "Refusing to overwrite dirty DogOps-managed target paths:" >&2
    echo "${dirty}" >&2
    echo "Commit/stash/review them first, or set DOGOPS_SYNC_ALLOW_DIRTY=1." >&2
    exit 3
  fi
fi

copy_dir() {
  local src="$1"
  local dst="$2"
  mkdir -p "${dst}"
  rsync -a --delete \
    --exclude '__pycache__/' \
    --exclude '.pytest_cache/' \
    --exclude '*.pyc' \
    "${src}/" "${dst}/"
}

copy_file() {
  local src="$1"
  local dst="$2"
  mkdir -p "$(dirname "${dst}")"
  rsync -a "${src}" "${dst}"
}

copy_dir "${repo_root}/dimos/experimental/dogops" \
  "${dimos_root}/dimos/experimental/dogops"
copy_file "${repo_root}/dimos/robot/unitree/go2/blueprints/agentic/unitree_go2_dogops.py" \
  "${dimos_root}/dimos/robot/unitree/go2/blueprints/agentic/unitree_go2_dogops.py"
copy_dir "${repo_root}/examples/dogops" \
  "${dimos_root}/examples/dogops"

cat <<EOF
DogOps synced into: ${dimos_root}

Next validation commands:
  cd ${dimos_root}
  uv run pytest dimos/robot/test_all_blueprints_generation.py
  uv run dimos list | rg dogops
  uv run pytest -q dimos/experimental/dogops
EOF
