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
    args = parser.parse_args()

    event = json.loads(args.event_file.read_text(encoding="utf-8"))
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
