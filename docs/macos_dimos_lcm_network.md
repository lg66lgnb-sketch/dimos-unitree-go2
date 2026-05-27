# macOS Dimos LCM Network Prep

DimOS Go2 simulation and replay can use LCM multicast on macOS. The local DimOS configurator expects multicast traffic for `224.0.0.0/4` to route through `lo0`, and it raises UDP socket limits so high-rate camera, lidar, map, and costmap streams are less likely to drop.

Use [scripts/macos_dimos_lcm_network.sh](../scripts/macos_dimos_lcm_network.sh) to inspect, snapshot, apply, and restore this state. Dry-run commands never run `sudo`.

## What It Changes

Apply mode runs these privileged commands after creating a snapshot:

```bash
sudo route delete -net 224.0.0.0/4 || true
sudo route add -net 224.0.0.0/4 -interface lo0
sudo sysctl -w kern.ipc.maxsockbuf=67108864
sudo sysctl -w net.inet.udp.recvspace=67108864
sudo sysctl -w net.inet.udp.maxdgram=67108864
```

The route change is for local multicast loopback. The sysctl changes are generally not persistent across reboot unless another local tool reapplies them. If macOS rejects a requested sysctl value as too large, the helper halves the value until macOS accepts it or keeps the current value. This mirrors DimOS' own macOS buffer configurator and avoids leaving the route half-applied just because the host has a lower socket-buffer ceiling.

## Status

```bash
./scripts/macos_dimos_lcm_network.sh status
```

Check that `224.0.0/4` appears on `lo0` in the multicast rows and that the DimOS-style multicast address `239.255.76.67` resolves to `interface: lo0`. The `224.0.0.251` probe is intentionally shown because it exposes mDNS-specific host routes; on macOS it may continue to resolve to Wi-Fi/Ethernet even when the broad `224.0.0/4` route is on `lo0`. The helper does not delete mDNS host routes by default because that can disrupt local discovery.

If either route resolves to a `utun` interface, a VPN/proxy path may be intercepting multicast. With Shadowrocket enabled, run status before and after toggling rules/proxy mode so you know whether multicast still stays on `lo0`.

## Snapshot

```bash
./scripts/macos_dimos_lcm_network.sh snapshot
```

Snapshots are written under:

```text
~/.dimos/macos-network-snapshots/
```

Each snapshot includes a shell-readable `snapshot.env` plus raw route, netstat, and sysctl command outputs. The snapshot records previous multicast interface/gateway when parseable and the exact prior values for:

- `kern.ipc.maxsockbuf`
- `net.inet.udp.recvspace`
- `net.inet.udp.maxdgram`

## Apply

Preview first:

```bash
./scripts/macos_dimos_lcm_network.sh dry-run-apply
```

Then run from an interactive Terminal:

```bash
./scripts/macos_dimos_lcm_network.sh apply
```

The script prints the exact privileged commands, asks you to type `APPLY`, then runs them with `sudo`. Use `--skip-snapshot` only if you already captured the state you want to restore to.

After applying, retry the native DimOS simulation:

```bash
cd /path/to/dimos
UV_CACHE_DIR=/private/tmp/dogops-uv-cache uv run dimos --simulation --viewer rerun --rerun-open none run unitree-go2
```

## Restore

Preview restore from the latest snapshot:

```bash
./scripts/macos_dimos_lcm_network.sh dry-run-restore
```

Restore from the latest snapshot:

```bash
./scripts/macos_dimos_lcm_network.sh restore
```

Restore from a specific snapshot:

```bash
./scripts/macos_dimos_lcm_network.sh restore ~/.dimos/macos-network-snapshots/<timestamp>/snapshot.env
```

Restore mode puts the sysctl values back exactly from the snapshot. For route state, it first deletes the DimOS `224.0.0.0/4` route. If the snapshot had a previous non-`lo0` interface, it best-effort restores that route. If the previous route was missing or ambiguous, it leaves the route deleted and prints:

```text
Toggle Wi-Fi/Ethernet or reboot to let macOS recreate the default multicast route.
```

Use that network toggle or reboot when you need the safest exact reset.

## Non-Privileged Smoke Test

The smoke test checks syntax, optional `shellcheck`, and dry-run output only:

```bash
./scripts/test_macos_dimos_lcm_network.sh
```

It does not run `sudo`, `apply`, or `restore`.
