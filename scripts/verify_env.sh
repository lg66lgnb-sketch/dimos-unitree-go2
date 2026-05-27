#!/usr/bin/env bash
set -euo pipefail

cd "${DOGOPS_DIMOS_ROOT:-$(pwd)}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"

command -v uv
command -v git
command -v rg
command -v jq

uv run python --version
uv run dimos list | rg 'unitree-go2'
uv run pytest -q dimos/utils/cli/test_apriltag.py
uv run dimos apriltag --ids '10,20,101-104' --size-mm 100 --family tag36h11 --out /tmp/dogops-tags.pdf
ls -lh /tmp/dogops-tags.pdf

if [[ -n "${GO2_IP:-}" ]]; then
  ping -c 3 "$GO2_IP"
  uv run dimos stop --force || true
  uv run dimos --viewer none run unitree-go2 -o "go2connection.ip=${GO2_IP}" --daemon
  uv run dimos status
  uv run dimos log -n 100
  uv run dimos stop --force
else
  echo "GO2_IP is not set; skipped real Go2 smoke."
fi

echo "Environment verification passed."
