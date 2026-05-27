#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Skipping macOS LCM network helper smoke test on non-Darwin host."
  exit 0
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
helper="${repo_root}/scripts/macos_dimos_lcm_network.sh"
tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/dimos-lcm-network-test.XXXXXX")"
trap 'rm -rf "${tmpdir}"' EXIT

bash -n "${helper}"
if command -v shellcheck >/dev/null 2>&1; then
  shellcheck "${helper}"
fi

"${helper}" dry-run-apply >"${tmpdir}/dry-run-apply.txt"
grep -q 'sudo route add -net 224.0.0.0/4 -interface lo0' "${tmpdir}/dry-run-apply.txt"
grep -q 'sudo sysctl -w kern.ipc.maxsockbuf=67108864' "${tmpdir}/dry-run-apply.txt"
grep -q 'falls back by halving' "${tmpdir}/dry-run-apply.txt"

cat >"${tmpdir}/snapshot.env" <<EOF
SNAPSHOT_TIMESTAMP=2026-05-27T00:00:00Z
SNAPSHOT_DIR=${tmpdir}
PREVIOUS_INTERFACE=en0
PREVIOUS_GATEWAY=link#14
SYSCTL_kern_ipc_maxsockbuf=8388608
SYSCTL_net_inet_udp_recvspace=786896
SYSCTL_net_inet_udp_maxdgram=9216
EOF

"${helper}" dry-run-restore "${tmpdir}/snapshot.env" >"${tmpdir}/dry-run-restore.txt"
grep -q 'sudo sysctl -w kern.ipc.maxsockbuf=8388608' "${tmpdir}/dry-run-restore.txt"
grep -q 'sudo route add -net 224.0.0.0/4 -interface en0' "${tmpdir}/dry-run-restore.txt"

cat >"${tmpdir}/malicious-snapshot.env" <<EOF
SNAPSHOT_TIMESTAMP=2026-05-27T00:00:00Z
SNAPSHOT_DIR=${tmpdir}
PREVIOUS_INTERFACE=\$(touch "${tmpdir}/snapshot-was-sourced")
PREVIOUS_GATEWAY=link#14
SYSCTL_kern_ipc_maxsockbuf=8388608
SYSCTL_net_inet_udp_recvspace=786896
SYSCTL_net_inet_udp_maxdgram=9216
EOF

"${helper}" dry-run-restore "${tmpdir}/malicious-snapshot.env" >"${tmpdir}/malicious-dry-run-restore.txt"
test ! -e "${tmpdir}/snapshot-was-sourced"
grep -q 'Previous multicast route was missing, lo0, or ambiguous.' "${tmpdir}/malicious-dry-run-restore.txt"
if grep -q 'snapshot-was-sourced' "${tmpdir}/malicious-dry-run-restore.txt"; then
  echo "unsafe snapshot interface leaked into dry-run restore commands" >&2
  exit 1
fi

echo "macOS LCM network helper smoke test passed."
