#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request


DEFAULT_URL = "http://127.0.0.1:8765/api/qr/events"
DEFAULT_EVENT = Path("examples/dogops/qr_cargo_event_sample.json")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Post a sample QR cargo event to a local DogOps dashboard."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="DogOps /api/qr/events URL")
    parser.add_argument(
        "--event-file",
        type=Path,
        default=DEFAULT_EVENT,
        help="JSON event file to POST",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("DOGOPS_DASHBOARD_TOKEN", ""),
        help="DogOps dashboard write token; defaults to DOGOPS_DASHBOARD_TOKEN",
    )
    parser.add_argument(
        "--cargo-id",
        help="Override qr_payload.cargo_id for the posted sample event",
    )
    parser.add_argument(
        "--location-node-id",
        help="Override qr_payload.location_node_id for the posted sample event",
    )
    parser.add_argument(
        "--pose-x",
        type=float,
        help="Map-frame x coordinate where the QR was detected",
    )
    parser.add_argument(
        "--pose-y",
        type=float,
        help="Map-frame y coordinate where the QR was detected",
    )
    parser.add_argument(
        "--pose-yaw",
        type=float,
        help="Map-frame yaw where the QR was detected",
    )
    args = parser.parse_args()

    event = json.loads(args.event_file.read_text(encoding="utf-8"))
    payload = event.get("qr_payload")
    if not isinstance(payload, dict):
        payload = {}
    payload = dict(payload)
    if args.cargo_id:
        payload["cargo_id"] = args.cargo_id
    if args.location_node_id:
        payload["location_node_id"] = args.location_node_id
    if payload:
        event["qr_payload"] = payload
        event["qr_payload_raw"] = json.dumps(payload, separators=(",", ":"))
    if args.pose_x is not None or args.pose_y is not None or args.pose_yaw is not None:
        pose = event.get("robot_pose_at_detection")
        if not isinstance(pose, dict):
            pose = {}
        pose = dict(pose)
        pose["frame"] = str(pose.get("frame") or "map")
        if args.pose_x is not None:
            pose["x"] = args.pose_x
        if args.pose_y is not None:
            pose["y"] = args.pose_y
        if args.pose_yaw is not None:
            pose["yaw"] = args.pose_yaw
        event["robot_pose_at_detection"] = pose

    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["X-DogOps-Control-Token"] = args.token
    else:
        print(
            "No dashboard token provided. Start DogOps with DOGOPS_DASHBOARD_TOKEN "
            "or pass --token; protected dashboards will return 403.",
            file=sys.stderr,
        )

    request = urllib.request.Request(
        args.url,
        data=json.dumps(event).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8"), file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    print()
    print("Demo flow:")
    print("1. Start DogOps dashboard with a known DOGOPS_DASHBOARD_TOKEN.")
    print("2. Run this script with the same --token.")
    print("3. Open the dashboard and confirm the QR Cargo panel and map overlay.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
