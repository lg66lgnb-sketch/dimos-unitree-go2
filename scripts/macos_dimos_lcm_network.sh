#!/usr/bin/env bash
set -euo pipefail

SNAPSHOT_ROOT="${DIMOS_MACOS_NETWORK_SNAPSHOT_DIR:-${HOME}/.dimos/macos-network-snapshots}"
LCM_ROUTE_NET="224.0.0.0/4"
LCM_ROUTE_TARGET_A="224.0.0.251"
LCM_ROUTE_TARGET_B="239.255.76.67"
LCM_INTERFACE="lo0"
SYSCTL_MAXSOCKBUF="kern.ipc.maxsockbuf"
SYSCTL_RECVSPACE="net.inet.udp.recvspace"
SYSCTL_MAXDGRAM="net.inet.udp.maxdgram"
REQUESTED_MAXSOCKBUF="67108864"
REQUESTED_RECVSPACE="67108864"
REQUESTED_MAXDGRAM="67108864"

usage() {
  cat <<'EOF'
Usage:
  scripts/macos_dimos_lcm_network.sh status
  scripts/macos_dimos_lcm_network.sh snapshot
  scripts/macos_dimos_lcm_network.sh dry-run-apply
  scripts/macos_dimos_lcm_network.sh apply [--skip-snapshot]
  scripts/macos_dimos_lcm_network.sh dry-run-restore [snapshot.env|snapshot-dir]
  scripts/macos_dimos_lcm_network.sh restore [snapshot.env|snapshot-dir]

Snapshot directory:
  ~/.dimos/macos-network-snapshots/

No sudo commands are run by dry-run-* actions.
EOF
}

shell_quote() {
  printf '%q' "$1"
}

require_macos() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "This helper is macOS-only because it inspects Darwin route/sysctl state." >&2
    exit 2
  fi
}

run_or_record() {
  local outfile="$1"
  shift
  {
    printf '$'
    printf ' %q' "$@"
    printf '\n\n'
    "$@"
  } >"${outfile}" 2>&1 || {
    local rc=$?
    printf '\n[command failed with exit code %s]\n' "${rc}" >>"${outfile}"
    return 0
  }
}

route_interface_from_file() {
  awk -F': ' '/interface:/{gsub(/^[ \t]+|[ \t]+$/, "", $2); print $2; exit}' "$1"
}

route_gateway_from_file() {
  awk -F': ' '/gateway:/{gsub(/^[ \t]+|[ \t]+$/, "", $2); print $2; exit}' "$1"
}

sysctl_value() {
  local key="$1"
  sysctl -n "${key}"
}

print_sysctls() {
  local key value
  for key in "${SYSCTL_MAXSOCKBUF}" "${SYSCTL_RECVSPACE}" "${SYSCTL_MAXDGRAM}"; do
    if value="$(sysctl_value "${key}" 2>&1)"; then
      printf '  %s=%s\n' "${key}" "${value}"
    else
      printf '  %s: unavailable (%s)\n' "${key}" "${value}"
    fi
  done
}

print_multicast_rows() {
  if ! netstat -rn -f inet 2>&1 | awk '
    $1 ~ /^224(\.|\/|$)/ { print; found=1 }
    $1 ~ /^239(\.|\/|$)/ { print; found=1 }
    $1 == "224/4" { print; found=1 }
    END { exit found ? 0 : 1 }
  '; then
    echo "  (no 224/4 or 239 multicast rows found)"
  fi
}

warn_if_netstat_utun() {
  local rows
  rows="$(netstat -rn -f inet 2>/dev/null | awk '
    $1 ~ /^224(\.|\/|$)/ { print }
    $1 ~ /^239(\.|\/|$)/ { print }
    $1 == "224/4" { print }
  ' || true)"
  if printf '%s\n' "${rows}" | grep -q 'utun'; then
    echo
    echo "WARNING: multicast route table contains a utun interface. A VPN/proxy such as Shadowrocket may be intercepting traffic."
  fi
}

print_route_status() {
  local target="$1"
  local output iface

  echo
  echo "Route for ${target}:"
  if output="$(route -n get "${target}" 2>&1)"; then
    printf '%s\n' "${output}" | sed 's/^/  /'
    iface="$(printf '%s\n' "${output}" | awk -F': ' '/interface:/{gsub(/^[ \t]+|[ \t]+$/, "", $2); print $2; exit}')"
    if [[ -z "${iface}" ]]; then
      echo "  WARNING: no interface field found in route output."
    elif [[ "${iface}" == "${LCM_INTERFACE}" ]]; then
      echo "  OK: ${target} resolves to ${LCM_INTERFACE}."
    elif [[ "${iface}" == utun* ]]; then
      echo "  WARNING: ${target} resolves to ${iface}. A VPN/proxy such as Shadowrocket may be intercepting multicast."
    else
      echo "  WARNING: ${target} resolves to ${iface}, not ${LCM_INTERFACE}."
    fi
  else
    echo "  route lookup failed:"
    printf '%s\n' "${output}" | sed 's/^/  /'
  fi
}

status() {
  print_route_status "${LCM_ROUTE_TARGET_A}"
  print_route_status "${LCM_ROUTE_TARGET_B}"

  echo
  echo "Matching multicast rows from netstat -rn -f inet:"
  print_multicast_rows | sed 's/^/  /'
  warn_if_netstat_utun

  echo
  echo "Current sysctl values:"
  print_sysctls
}

snapshot_sysctl_value() {
  local key="$1"
  local value
  if value="$(sysctl_value "${key}" 2>/dev/null)"; then
    printf '%s\n' "${value}"
  else
    printf ''
  fi
}

create_snapshot() {
  local timestamp safe_timestamp snapshot_dir route_a route_b netstat_file multicast_file sysctl_file env_file
  timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  safe_timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
  snapshot_dir="${SNAPSHOT_ROOT}/${safe_timestamp}"
  mkdir -p "${snapshot_dir}"

  route_a="${snapshot_dir}/route_${LCM_ROUTE_TARGET_A}.txt"
  route_b="${snapshot_dir}/route_${LCM_ROUTE_TARGET_B}.txt"
  netstat_file="${snapshot_dir}/netstat_rn_f_inet.txt"
  multicast_file="${snapshot_dir}/netstat_multicast_rows.txt"
  sysctl_file="${snapshot_dir}/sysctl_values.txt"
  env_file="${snapshot_dir}/snapshot.env"

  run_or_record "${route_a}" route -n get "${LCM_ROUTE_TARGET_A}"
  run_or_record "${route_b}" route -n get "${LCM_ROUTE_TARGET_B}"
  run_or_record "${netstat_file}" netstat -rn -f inet
  run_or_record "${sysctl_file}" sysctl -n "${SYSCTL_MAXSOCKBUF}" "${SYSCTL_RECVSPACE}" "${SYSCTL_MAXDGRAM}"
  awk '
    $1 ~ /^224(\.|\/|$)/ { print; found=1 }
    $1 ~ /^239(\.|\/|$)/ { print; found=1 }
    $1 == "224/4" { print; found=1 }
    END { if (!found) print "(no 224/4 or 239 multicast rows found)" }
  ' "${netstat_file}" >"${multicast_file}"

  local previous_interface previous_gateway maxsockbuf recvspace maxdgram
  previous_interface="$(route_interface_from_file "${route_a}")"
  previous_gateway="$(route_gateway_from_file "${route_a}")"
  maxsockbuf="$(snapshot_sysctl_value "${SYSCTL_MAXSOCKBUF}")"
  recvspace="$(snapshot_sysctl_value "${SYSCTL_RECVSPACE}")"
  maxdgram="$(snapshot_sysctl_value "${SYSCTL_MAXDGRAM}")"

  cat >"${env_file}" <<EOF
# shellcheck shell=bash
# Dimos macOS LCM network snapshot.
# Source this file only if you trust the local snapshot directory.
SNAPSHOT_TIMESTAMP=$(shell_quote "${timestamp}")
SNAPSHOT_DIR=$(shell_quote "${snapshot_dir}")
ROUTE_TARGET_A=$(shell_quote "${LCM_ROUTE_TARGET_A}")
ROUTE_TARGET_B=$(shell_quote "${LCM_ROUTE_TARGET_B}")
PREVIOUS_INTERFACE=$(shell_quote "${previous_interface}")
PREVIOUS_GATEWAY=$(shell_quote "${previous_gateway}")
SYSCTL_${SYSCTL_MAXSOCKBUF//./_}=$(shell_quote "${maxsockbuf}")
SYSCTL_${SYSCTL_RECVSPACE//./_}=$(shell_quote "${recvspace}")
SYSCTL_${SYSCTL_MAXDGRAM//./_}=$(shell_quote "${maxdgram}")
EOF

  echo "Snapshot created: ${env_file}"
  if [[ -z "${maxsockbuf}" || -z "${recvspace}" || -z "${maxdgram}" ]]; then
    echo "WARNING: one or more sysctl values could not be read; restore will refuse exact sysctl restore from this snapshot." >&2
  fi
}

latest_snapshot_env() {
  if [[ ! -d "${SNAPSHOT_ROOT}" ]]; then
    return 1
  fi
  find "${SNAPSHOT_ROOT}" -type f -name snapshot.env -print | sort | tail -n 1
}

resolve_snapshot_env() {
  local requested="${1:-}" snapshot_env
  if [[ -n "${requested}" ]]; then
    if [[ -d "${requested}" ]]; then
      snapshot_env="${requested}/snapshot.env"
    else
      snapshot_env="${requested}"
    fi
  else
    snapshot_env="$(latest_snapshot_env || true)"
  fi

  if [[ -z "${snapshot_env}" || ! -f "${snapshot_env}" ]]; then
    echo "No snapshot found. Run: $0 snapshot" >&2
    exit 1
  fi
  printf '%s\n' "${snapshot_env}"
}

print_apply_commands() {
  cat <<EOF
sudo route delete -net ${LCM_ROUTE_NET} || true
sudo route add -net ${LCM_ROUTE_NET} -interface ${LCM_INTERFACE}
sudo sysctl -w ${SYSCTL_MAXSOCKBUF}=${REQUESTED_MAXSOCKBUF}  # falls back by halving if macOS rejects the value
sudo sysctl -w ${SYSCTL_RECVSPACE}=${REQUESTED_RECVSPACE}    # falls back by halving if macOS rejects the value
sudo sysctl -w ${SYSCTL_MAXDGRAM}=${REQUESTED_MAXDGRAM}      # falls back by halving if macOS rejects the value
EOF
}

confirm_or_exit() {
  local token="$1"
  local prompt="$2"
  if [[ ! -t 0 ]]; then
    echo "Refusing to run privileged commands without an interactive terminal. Use dry-run mode to print commands." >&2
    exit 1
  fi
  echo
  read -r -p "${prompt} Type ${token} to continue: " reply
  if [[ "${reply}" != "${token}" ]]; then
    echo "Aborted."
    exit 1
  fi
}

verify_at_least() {
  local key="$1"
  local requested="$2"
  local actual
  actual="$(sysctl_value "${key}")"
  if [[ "${actual}" =~ ^[0-9]+$ && "${actual}" -ge "${requested}" ]]; then
    echo "OK: ${key}=${actual} (requested at least ${requested})"
  else
    echo "WARNING: ${key}=${actual}; requested at least ${requested}."
  fi
}

set_sysctl_best_effort() {
  local key="$1"
  local target="$2"
  local current attempt output
  current="$(sysctl_value "${key}")"
  attempt="${target}"

  while [[ "${attempt}" =~ ^[0-9]+$ && "${current}" =~ ^[0-9]+$ && "${attempt}" -gt "${current}" ]]; do
    if output="$(sudo sysctl -w "${key}=${attempt}" 2>&1)"; then
      printf '%s\n' "${output}"
      return 0
    fi
    echo "WARNING: macOS rejected ${key}=${attempt}: ${output}" >&2
    attempt="$((attempt / 2))"
  done

  echo "Keeping ${key}=${current}; macOS did not accept a higher value from requested ${target}." >&2
}

verify_apply() {
  local target output iface
  for target in "${LCM_ROUTE_TARGET_A}" "${LCM_ROUTE_TARGET_B}"; do
    echo
    echo "Verifying route for ${target}:"
    if output="$(route -n get "${target}" 2>&1)"; then
      printf '%s\n' "${output}" | sed 's/^/  /'
      iface="$(printf '%s\n' "${output}" | awk -F': ' '/interface:/{gsub(/^[ \t]+|[ \t]+$/, "", $2); print $2; exit}')"
      if [[ "${iface}" == "${LCM_INTERFACE}" ]]; then
        echo "OK: ${target} resolves to ${LCM_INTERFACE}."
      else
        echo "WARNING: ${target} resolves to ${iface:-unknown}, not ${LCM_INTERFACE}."
      fi
    else
      echo "WARNING: route lookup failed for ${target}:"
      printf '%s\n' "${output}" | sed 's/^/  /'
    fi
  done

  echo
  echo "Verifying sysctl values:"
  verify_at_least "${SYSCTL_MAXSOCKBUF}" "${REQUESTED_MAXSOCKBUF}"
  verify_at_least "${SYSCTL_RECVSPACE}" "${REQUESTED_RECVSPACE}"
  verify_at_least "${SYSCTL_MAXDGRAM}" "${REQUESTED_MAXDGRAM}"
}

apply_setup() {
  local skip_snapshot="0"
  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      --skip-snapshot)
        skip_snapshot="1"
        ;;
      *)
        echo "Unknown apply option: $1" >&2
        usage
        exit 1
        ;;
    esac
    shift
  done

  if [[ "${skip_snapshot}" != "1" ]]; then
    create_snapshot
  fi

  echo
  echo "About to apply Dimos macOS LCM network setup:"
  print_apply_commands | sed 's/^/  /'
  confirm_or_exit "APPLY" "This will run sudo route/sysctl commands."

  sudo route delete -net "${LCM_ROUTE_NET}" || true
  sudo route add -net "${LCM_ROUTE_NET}" -interface "${LCM_INTERFACE}"
  set_sysctl_best_effort "${SYSCTL_MAXSOCKBUF}" "${REQUESTED_MAXSOCKBUF}"
  set_sysctl_best_effort "${SYSCTL_RECVSPACE}" "${REQUESTED_RECVSPACE}"
  set_sysctl_best_effort "${SYSCTL_MAXDGRAM}" "${REQUESTED_MAXDGRAM}"
  verify_apply
}

snapshot_var_name_for_sysctl() {
  local key="$1"
  printf 'SYSCTL_%s' "${key//./_}"
}

snapshot_value() {
  local snapshot_env="$1"
  local key="$2"
  local line value
  line="$(grep -E "^${key}=" "${snapshot_env}" | tail -n 1 || true)"
  value="${line#*=}"
  value="${value#\"}"
  value="${value%\"}"
  value="${value#\'}"
  value="${value%\'}"
  printf '%s\n' "${value}"
}

is_safe_interface_name() {
  local value="$1"
  [[ "${value}" =~ ^[A-Za-z0-9_.:-]+$ ]]
}

require_snapshot_sysctl_value() {
  local key="$1"
  local value="$2"
  if [[ ! "${value}" =~ ^[0-9]+$ ]]; then
    echo "Snapshot does not contain a numeric value for ${key}; refusing exact sysctl restore." >&2
    exit 1
  fi
}

restore_commands() {
  local snapshot_env="$1"

  local old_maxsockbuf old_recvspace old_maxdgram previous_interface
  old_maxsockbuf="$(snapshot_value "${snapshot_env}" "$(snapshot_var_name_for_sysctl "${SYSCTL_MAXSOCKBUF}")")"
  old_recvspace="$(snapshot_value "${snapshot_env}" "$(snapshot_var_name_for_sysctl "${SYSCTL_RECVSPACE}")")"
  old_maxdgram="$(snapshot_value "${snapshot_env}" "$(snapshot_var_name_for_sysctl "${SYSCTL_MAXDGRAM}")")"
  previous_interface="$(snapshot_value "${snapshot_env}" "PREVIOUS_INTERFACE")"
  require_snapshot_sysctl_value "${SYSCTL_MAXSOCKBUF}" "${old_maxsockbuf}"
  require_snapshot_sysctl_value "${SYSCTL_RECVSPACE}" "${old_recvspace}"
  require_snapshot_sysctl_value "${SYSCTL_MAXDGRAM}" "${old_maxdgram}"

  cat <<EOF
sudo route delete -net ${LCM_ROUTE_NET} || true
sudo sysctl -w ${SYSCTL_MAXSOCKBUF}=${old_maxsockbuf}
sudo sysctl -w ${SYSCTL_RECVSPACE}=${old_recvspace}
sudo sysctl -w ${SYSCTL_MAXDGRAM}=${old_maxdgram}
EOF

  if [[ -n "${previous_interface}" && "${previous_interface}" != "${LCM_INTERFACE}" ]] && is_safe_interface_name "${previous_interface}"; then
    printf 'sudo route add -net %s -interface %s\n' "${LCM_ROUTE_NET}" "${previous_interface}"
  else
    echo '# Previous multicast route was missing, lo0, or ambiguous.'
    echo '# Toggle Wi-Fi/Ethernet or reboot to let macOS recreate the default multicast route.'
  fi
}

restore_setup() {
  local snapshot_arg=""
  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      *)
        if [[ -z "${snapshot_arg}" ]]; then
          snapshot_arg="$1"
        else
          echo "Unknown restore option: $1" >&2
          usage
          exit 1
        fi
        ;;
    esac
    shift
  done

  local snapshot_env
  snapshot_env="$(resolve_snapshot_env "${snapshot_arg}")"

  local old_maxsockbuf old_recvspace old_maxdgram previous_interface
  old_maxsockbuf="$(snapshot_value "${snapshot_env}" "$(snapshot_var_name_for_sysctl "${SYSCTL_MAXSOCKBUF}")")"
  old_recvspace="$(snapshot_value "${snapshot_env}" "$(snapshot_var_name_for_sysctl "${SYSCTL_RECVSPACE}")")"
  old_maxdgram="$(snapshot_value "${snapshot_env}" "$(snapshot_var_name_for_sysctl "${SYSCTL_MAXDGRAM}")")"
  previous_interface="$(snapshot_value "${snapshot_env}" "PREVIOUS_INTERFACE")"
  require_snapshot_sysctl_value "${SYSCTL_MAXSOCKBUF}" "${old_maxsockbuf}"
  require_snapshot_sysctl_value "${SYSCTL_RECVSPACE}" "${old_recvspace}"
  require_snapshot_sysctl_value "${SYSCTL_MAXDGRAM}" "${old_maxdgram}"

  echo "Using snapshot: ${snapshot_env}"
  echo
  echo "About to restore macOS route/sysctl state:"
  restore_commands "${snapshot_env}" | sed 's/^/  /'
  confirm_or_exit "RESTORE" "This will run sudo route/sysctl commands."

  sudo route delete -net "${LCM_ROUTE_NET}" || true
  sudo sysctl -w "${SYSCTL_MAXSOCKBUF}=${old_maxsockbuf}"
  sudo sysctl -w "${SYSCTL_RECVSPACE}=${old_recvspace}"
  sudo sysctl -w "${SYSCTL_MAXDGRAM}=${old_maxdgram}"

  if [[ -n "${previous_interface}" && "${previous_interface}" != "${LCM_INTERFACE}" ]] && is_safe_interface_name "${previous_interface}"; then
    sudo route add -net "${LCM_ROUTE_NET}" -interface "${previous_interface}"
  else
    echo
    echo "Toggle Wi-Fi/Ethernet or reboot to let macOS recreate the default multicast route."
  fi

  echo
  echo "Current status after restore:"
  status
}

dry_run_apply() {
  echo "Would create a snapshot under: ${SNAPSHOT_ROOT}"
  echo "Would run:"
  print_apply_commands | sed 's/^/  /'
}

dry_run_restore() {
  local snapshot_env
  snapshot_env="$(resolve_snapshot_env "${1:-}")"
  echo "Using snapshot: ${snapshot_env}"
  echo "Would run:"
  restore_commands "${snapshot_env}" | sed 's/^/  /'
}

main() {
  require_macos
  local command="${1:-}"
  if [[ -z "${command}" ]]; then
    usage
    exit 1
  fi
  shift

  case "${command}" in
    status)
      status
      ;;
    snapshot)
      create_snapshot
      ;;
    dry-run-apply)
      dry_run_apply
      ;;
    apply)
      apply_setup "$@"
      ;;
    dry-run-restore)
      dry_run_restore "${1:-}"
      ;;
    restore)
      restore_setup "$@"
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      echo "Unknown command: ${command}" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
