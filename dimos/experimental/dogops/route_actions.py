from __future__ import annotations

from pathlib import Path
import html
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


def execute_route_action(
    action: EditableRouteAction,
    *,
    run_dir: str | Path,
    route_run_id: str,
    waypoint_id: str,
) -> RouteActionResult:
    if action.kind == "scan_tags":
        expected = [int(tag) for tag in action.args.get("expected", [])]
        return RouteActionResult(
            ok=True,
            note=f"tag scan demo result: {len(expected)} expected",
            payload={"expected_tag_ids": expected, "detected_tag_ids": expected, "source": "demo"},
        )
    if action.kind == "scan_qr":
        expected = [str(item) for item in action.args.get("expected", [])]
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
        )
    if action.kind == "capture_image":
        image_path = _write_placeholder_image(
            run_dir=Path(run_dir),
            route_run_id=route_run_id,
            waypoint_id=waypoint_id,
            action=action,
        )
        return RouteActionResult(
            ok=True,
            note="placeholder dog-camera image captured",
            payload={"source": "demo_placeholder", "path": str(image_path)},
            evidence=[
                {
                    "kind": "image",
                    "path": str(image_path),
                    "mime_type": "image/svg+xml",
                    "metadata": {
                        "source": "demo_placeholder",
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
