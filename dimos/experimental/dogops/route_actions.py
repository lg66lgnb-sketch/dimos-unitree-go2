from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import html
import os
import shutil
import time
from typing import Any, Literal

from pydantic import Field

from dimos.experimental.dogops.models import DogOpsModel


RouteActionKind = Literal[
    "scan_tags",
    "scan_qr",
    "capture_image",
    "inspect_asset",
    "verify_work_order",
    "wait",
    "operator_prompt",
]


class EditableRouteAction(DogOpsModel):
    id: str
    kind: RouteActionKind
    label: str | None = None
    required: bool = True
    timeout_s: float = 5.0
    args: dict[str, Any] = Field(default_factory=dict)


class RouteActionResult(DogOpsModel):
    ok: bool
    state: Literal["completed", "failed", "skipped"] = "completed"
    note: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)


ScanZoneHandler = Callable[[str], str | dict[str, Any]]


def execute_route_action(
    action: EditableRouteAction,
    *,
    run_dir: str | Path,
    route_run_id: str,
    waypoint_id: str,
    target_id: str | None = None,
    scan_zone_handler: ScanZoneHandler | None = None,
) -> RouteActionResult:
    if action.kind == "scan_tags":
        expected = [int(tag) for tag in action.args.get("expected", [])]
        return RouteActionResult(
            ok=True,
            note=f"tag scan demo result: {len(expected)} expected",
            payload={"expected_tag_ids": expected, "detected_tag_ids": expected, "source": "demo"},
            evidence=[
                {
                    "kind": "tag_detection",
                    "path": None,
                    "mime_type": "application/json",
                    "metadata": {
                        "source": "demo",
                        "expected_tag_ids": expected,
                        "detected_tag_ids": expected,
                    },
                }
            ],
        )
    if action.kind == "scan_qr":
        expected = [str(item) for item in action.args.get("expected", [])]
        zone_id = _scan_zone_id_for_action(action, target_id=target_id, waypoint_id=waypoint_id)
        if scan_zone_handler is not None and zone_id:
            scan_result = _call_scan_zone(scan_zone_handler, zone_id)
            if scan_result.get("ok") is True:
                return _qr_result_from_scan_zone(expected, scan_result)
            if not expected:
                return RouteActionResult(
                    ok=False,
                    state="failed",
                    note=f"QR scan zone failed: {scan_result.get('error') or 'scan_zone_failed'}",
                    payload={"source": "scan_zone", "zone_id": zone_id, "scan_zone": scan_result},
                )
        payloads = expected
        if not payloads and action.args.get("payload"):
            payloads = [str(action.args["payload"])]
        if not payloads:
            return RouteActionResult(
                ok=False,
                state="failed",
                note="QR scan configured without expected payloads",
                payload={"source": "not_configured"},
            )
        return RouteActionResult(
            ok=True,
            note=f"QR scan demo result: {len(payloads)} payloads",
            payload={"expected_payloads": payloads, "detected_payloads": payloads, "source": "demo"},
            evidence=[
                {
                    "kind": "qr_detection",
                    "path": None,
                    "mime_type": "application/json",
                    "metadata": {
                        "source": "demo",
                        "expected_payloads": payloads,
                        "detected_payloads": payloads,
                    },
                }
            ],
        )
    if action.kind == "capture_image":
        image_path, source, mime_type = _capture_image_path(
            run_dir=Path(run_dir),
            route_run_id=route_run_id,
            waypoint_id=waypoint_id,
            action=action,
        )
        return RouteActionResult(
            ok=True,
            note=(
                "configured Go2 camera image captured"
                if source == "go2_camera_configured"
                else "placeholder dog-camera image captured"
            ),
            payload={"source": source, "path": str(image_path)},
            evidence=[
                {
                    "kind": "image",
                    "path": str(image_path),
                    "mime_type": mime_type,
                    "metadata": {
                        "source": source,
                        "waypoint_id": waypoint_id,
                        "action_id": action.id,
                    },
                }
            ],
        )
    if action.kind == "wait":
        return RouteActionResult(
            ok=True,
            note=f"wait completed ({float(action.args.get('seconds', 0.0)):.1f}s demo)",
            payload={"seconds": float(action.args.get("seconds", 0.0)), "source": "demo"},
        )
    if action.kind in {"inspect_asset", "verify_work_order", "operator_prompt"}:
        return RouteActionResult(
            ok=True,
            note=f"{action.kind} completed by deterministic demo handler",
            payload={"source": "demo", **action.args},
        )
    return RouteActionResult(ok=False, state="failed", note=f"unsupported action: {action.kind}")


def _scan_zone_id_for_action(
    action: EditableRouteAction,
    *,
    target_id: str | None,
    waypoint_id: str,
) -> str:
    for key in ("zone_id", "target_id", "target"):
        value = action.args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return (target_id or waypoint_id).strip()


def _call_scan_zone(handler: ScanZoneHandler, zone_id: str) -> dict[str, Any]:
    raw = handler(zone_id)
    if isinstance(raw, str):
        payload = json.loads(raw)
    else:
        payload = raw
    if not isinstance(payload, dict):
        raise ValueError("scan_zone handler returned a non-object payload")
    return payload


def _qr_result_from_scan_zone(
    expected: list[str],
    scan_result: dict[str, Any],
) -> RouteActionResult:
    detected_payloads = [str(item) for item in scan_result.get("package_ids") or []]
    detected_tag_ids = [int(tag) for tag in scan_result.get("visible_tag_ids") or []]
    zone_id = str(scan_result.get("zone_id") or "")
    source = str(scan_result.get("source") or "scan_zone")
    return RouteActionResult(
        ok=True,
        note=(
            f"QR scan used scan_zone {zone_id} via {source}: "
            f"{len(detected_payloads)} package payloads"
        ),
        payload={
            "expected_payloads": expected,
            "detected_payloads": detected_payloads,
            "detected_tag_ids": detected_tag_ids,
            "source": "scan_zone",
            "scan_zone_source": source,
            "zone_id": zone_id,
            "scan_zone": scan_result,
        },
        evidence=[
            {
                "kind": "qr_detection",
                "path": None,
                "mime_type": "application/json",
                "metadata": {
                    "source": "scan_zone",
                    "scan_zone_source": source,
                    "zone_id": zone_id,
                    "expected_payloads": expected,
                    "detected_payloads": detected_payloads,
                    "detected_tag_ids": detected_tag_ids,
                    "scan_zone": scan_result,
                },
            }
        ],
    )


def _capture_image_path(
    *,
    run_dir: Path,
    route_run_id: str,
    waypoint_id: str,
    action: EditableRouteAction,
) -> tuple[Path, str, str]:
    configured = action.args.get("image_path") or os.environ.get("DOGOPS_GO2_CAMERA_IMAGE_PATH")
    if configured:
        source = Path(str(configured)).expanduser()
        if source.exists() and source.is_file():
            evidence_dir = run_dir / "route_runs" / route_run_id / "evidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            suffix = source.suffix or ".img"
            destination = evidence_dir / f"{waypoint_id}-{action.id}{suffix}"
            shutil.copyfile(source, destination)
            return destination, "go2_camera_configured", _mime_type_for_suffix(suffix)
    return (
        _write_placeholder_image(
            run_dir=run_dir,
            route_run_id=route_run_id,
            waypoint_id=waypoint_id,
            action=action,
        ),
        "demo_placeholder",
        "image/svg+xml",
    )


def _mime_type_for_suffix(suffix: str) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }.get(suffix.lower(), "application/octet-stream")


def _write_placeholder_image(
    *,
    run_dir: Path,
    route_run_id: str,
    waypoint_id: str,
    action: EditableRouteAction,
) -> Path:
    evidence_dir = run_dir / "route_runs" / route_run_id / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / f"{waypoint_id}-{action.id}.svg"
    title = html.escape(str(action.label or action.id))
    target = html.escape(str(action.args.get("target") or waypoint_id))
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    path.write_text(
        f"""<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" viewBox="0 0 960 540">
  <rect width="960" height="540" fill="#111827"/>
  <rect x="42" y="42" width="876" height="456" rx="14" fill="#1f2937" stroke="#64748b" stroke-width="3"/>
  <path d="M92 386 L290 242 L430 330 L595 188 L868 388" fill="none" stroke="#38bdf8" stroke-width="10" stroke-linecap="round"/>
  <circle cx="692" cy="196" r="54" fill="#facc15" opacity="0.9"/>
  <rect x="118" y="116" width="180" height="120" rx="8" fill="#334155" stroke="#94a3b8" stroke-width="4"/>
  <rect x="344" y="112" width="120" height="168" rx="8" fill="#475569" stroke="#94a3b8" stroke-width="4"/>
  <rect x="508" y="126" width="168" height="112" rx="8" fill="#334155" stroke="#94a3b8" stroke-width="4"/>
  <text x="78" y="82" fill="#e5e7eb" font-family="Menlo, monospace" font-size="24">DOGOPS GO2 CAMERA PLACEHOLDER</text>
  <text x="78" y="454" fill="#bae6fd" font-family="Menlo, monospace" font-size="22">target={target}</text>
  <text x="78" y="482" fill="#cbd5e1" font-family="Menlo, monospace" font-size="18">action={title} / {html.escape(timestamp)}</text>
</svg>
""",
        encoding="utf-8",
    )
    return path
