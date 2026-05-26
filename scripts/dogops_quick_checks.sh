#!/usr/bin/env bash
set -euo pipefail

export UV_CACHE_DIR="${UV_CACHE_DIR:-${TMPDIR:-/tmp}/dogops-uv-cache}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"

uv run pytest -q dimos/experimental/dogops
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
cat .dogops/runs/latest/report.md
if uv run ruff --version >/dev/null 2>&1; then
  uv run ruff check dimos/experimental/dogops dimos/robot
else
  echo "Skipping ruff: executable is unavailable; rely on tests plus git diff --check until lint tooling is installed." >&2
fi
if uv run dimos list >/tmp/dogops-dimos-list.txt 2>/tmp/dogops-dimos-list.err; then
  if ! rg dogops /tmp/dogops-dimos-list.txt; then
    echo "DogOps is not present in dimos list; full DimOS registry integration is still pending." >&2
    exit 1
  fi
else
  echo "Skipping dimos list: dimos console script is unavailable. Run this in the full DimOS checkout before final."
fi

echo "DogOps quick checks complete."
