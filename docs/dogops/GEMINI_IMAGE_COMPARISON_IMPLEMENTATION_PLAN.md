# Gemini Image Comparison Implementation Plan

## Scope

DogOps should be able to send images captured during a route run to Gemini, receive a structured interpretation, and compare the current image with a prior image from the same waypoint. This is an optional cloud-assisted inspection feature: the base route execution, evidence capture, and dashboard must continue to work without `GEMINI_API_KEY` or internet.

Primary source of truth remains `SPEC.md`. This plan extends the existing route-run history and action-evidence system rather than replacing it.

## Current State

- Route waypoint actions already support `capture_image`.
- `capture_image` stores image evidence as a file under:

```text
.dogops/runs/<run_id>/route_runs/<route_run_id>/evidence/
```

- `RouteRunStore.record_evidence(...)` stores indexed metadata in the global local SQLite DB and mirrors per-run JSONL evidence.
- Until real Go2 camera frames are wired, `capture_image` uses either `DOGOPS_GO2_CAMERA_IMAGE_PATH` or a clearly labeled placeholder demo image.
- There is no VLM analysis action yet, and no baseline-image lookup helper for "same waypoint in a previous run."

## Product Goal

Add a route action that can do this during or after a route run:

```text
capture image at waypoint
-> find best previous image for the same waypoint
-> send current + baseline image to Gemini
-> store structured interpretation/comparison
-> show the result in route-run evidence, timeline, and dashboard history
```

The first implementation should prioritize comparison by the same waypoint. Broader fallbacks are allowed, but they must be explicit and labeled in the analysis metadata.

## External API Notes

Use the official Gemini API as the integration target:

- Gemini supports multimodal image prompting for image captioning, classification, visual question answering, object detection, segmentation, and related image tasks: <https://ai.google.dev/gemini-api/docs/image-understanding>
- For image inputs, inline image data is appropriate for smaller requests under the documented request-size limit; the File API is recommended for larger images or reuse across multiple requests: <https://ai.google.dev/gemini-api/docs/image-understanding>
- Use structured JSON output with `response_mime_type=application/json` and a JSON schema so DogOps can persist and validate the result deterministically: <https://ai.google.dev/gemini-api/docs/structured-output>

Do not log, persist, or display `GEMINI_API_KEY`.

## Proposed Route Action

Add a new action kind:

```text
gemini_inspect_image
```

Action arguments:

```json
{
  "prompt": "Inspect this waypoint for physical changes, safety issues, package changes, and work-order evidence.",
  "baseline_policy": "same_waypoint_latest_previous",
  "require_baseline": false,
  "model": "gemini-2.5-flash",
  "max_image_bytes_inline": 20000000
}
```

Execution behavior:

1. Locate the current image evidence for this route run and waypoint.
2. Locate the baseline image evidence from previous route runs.
3. If no baseline exists and `require_baseline=false`, ask Gemini to interpret the current image only.
4. If no baseline exists and `require_baseline=true`, mark the action failed/skipped according to `required`.
5. Send image(s), route context, waypoint context, and a strict JSON schema to Gemini.
6. Persist the Gemini response as route-run evidence and as a timeline event.

`capture_image` should remain focused on capture/storage. `gemini_inspect_image` should remain focused on analysis. A route can include both actions at the same waypoint.

## Baseline Matching

For now, use this order:

1. Same `waypoint_id` in a previous route run, most recent before the current route run.
2. Same `route_id` + same `waypoint_id`, if the route id is available in evidence/run metadata.
3. Same `target_id` in image evidence metadata.
4. Nearest pose fallback within a conservative tolerance, for example 0.3 m, only if both images have pose metadata.

The selected baseline must be recorded in the analysis metadata:

```json
{
  "baseline_policy": "same_waypoint_latest_previous",
  "baseline_match": "same_waypoint",
  "baseline_evidence_id": "EVD-...",
  "baseline_route_run_id": "RR-...",
  "baseline_created_at": 1770000000.0
}
```

If the operator asks for "yesterday," prefer evidence from the previous calendar day or a 12-36 hour window. If none exists, use the most recent previous matching waypoint and label the match as `latest_previous_same_waypoint`.

## Structured Gemini Output

Create a Pydantic model and JSON schema, for example:

```text
GeminiImageInspection
  schema_version: int
  ok: bool
  summary: str
  current_description: str
  baseline_description: str | None
  changed: bool
  change_summary: str
  change_type: no_change | object_added | object_removed | moved | damaged | blocked | unclear | other
  severity: info | p3 | p2 | p1
  confidence: float
  observations: list[str]
  possible_incident: bool
  recommended_action: str
  compared_evidence_ids: list[str]
  limitations: list[str]
```

The prompt must ask Gemini to be conservative:

- Do not infer identities or people.
- Do not claim a change unless visible evidence supports it.
- Say `unclear` when image quality or alignment is insufficient.
- Prefer facility/asset/package/work-order language.

## Persistence

Keep image bytes as files. Do not store image blobs in SQLite.

Store Gemini analysis as a JSON file:

```text
.dogops/runs/<run_id>/route_runs/<route_run_id>/evidence/<waypoint_id>-<action_id>-gemini.json
```

Record it through `RouteRunStore.record_evidence(...)`:

```text
kind = "gemini_vision_analysis"
path = <analysis json path>
mime_type = "application/json"
metadata = {
  "model": "...",
  "current_evidence_id": "...",
  "baseline_evidence_id": "...",
  "baseline_match": "...",
  "waypoint_id": "...",
  "action_id": "...",
  "changed": true,
  "severity": "p2"
}
```

Also emit a route-run event:

```text
kind = "action"
state = "completed" | "failed" | "skipped"
payload.analysis_evidence_id = "EVD-..."
note = "Gemini found no visible change" or concise summary
```

## Implementation Phases

### Phase 1: Evidence Lookup

- Add helpers to `RouteRunStore`:
  - `latest_image_evidence_for_waypoint(...)`
  - `image_evidence_for_route_run_waypoint(...)`
  - optional nearest-pose fallback when metadata contains pose.
- Ensure `capture_image` metadata includes:
  - `route_run_id`
  - `waypoint_id`
  - `action_id`
  - `target`
  - `route_id` when available
  - `pose` when available
  - `source`

Tests:

- Finds previous image for the same waypoint across two route runs.
- Ignores current route run as a baseline.
- Falls back to target or nearest pose only when same-waypoint match is unavailable.

### Phase 2: Gemini Client

- Add `dimos/experimental/dogops/gemini_vision.py`.
- Use `GEMINI_API_KEY` from the environment.
- Use REST or the existing project dependency set; do not add new dependencies unless needed.
- Prefer inline image input first for small local evidence files.
- Validate structured output with Pydantic before storing it.
- Return a clear unavailable result when:
  - `GEMINI_API_KEY` is missing,
  - image file is missing,
  - MIME type is unsupported,
  - network/API call fails,
  - Gemini returns invalid JSON.

Tests:

- Missing API key returns `gemini_unavailable` without network.
- Mocked successful Gemini response validates and persists.
- Invalid Gemini JSON records a failed action and does not create analysis evidence.

### Phase 3: Route Action Execution

- Extend `RouteActionKind` with `gemini_inspect_image`.
- Add execution branch in `execute_route_action(...)`.
- The action should analyze the latest image evidence for the same route run + waypoint, not silently capture a new image.
- If no current image evidence exists, return a clear failed/skipped result recommending a preceding `capture_image` action.
- Store analysis evidence and return it in `RouteActionResult.evidence`.

Tests:

- `capture_image` then `gemini_inspect_image` records image evidence plus analysis evidence.
- `gemini_inspect_image` without a prior image fails with a useful message.
- Baseline/no-baseline paths are both covered.

### Phase 4: Dashboard

- Add `Gemini Inspect` to the waypoint action buttons.
- Show Gemini analysis evidence in route-run detail/current timeline.
- Add a compact dashboard rendering:
  - summary,
  - changed/no-change,
  - severity,
  - confidence,
  - baseline match used,
  - links/paths for current and baseline evidence.
- Never expose the API key in HTML, JSON endpoints, logs, or error text.

Tests:

- Static HTML contains the new action button.
- Route action authoring persists `gemini_inspect_image`.
- Route-run evidence endpoint returns `gemini_vision_analysis`.

### Phase 5: Real Camera Integration

- Keep the first Gemini implementation compatible with placeholder/configured image evidence.
- Separately wire real Go2 camera frames into the existing `capture_image` hook.
- When real frames are available, store frame source and camera metadata in image evidence.
- Do not claim real visual inspection until the route run has real image evidence source metadata.

## Safety And Privacy

- Gemini is optional; base demo must run without cloud keys.
- No secrets in SQLite, JSONL, dashboard HTML, logs, PR descriptions, or screenshots.
- Image evidence may contain sensitive facilities data. Keep it local by default.
- Add a dashboard/report label when an analysis used a demo placeholder image.
- Gemini output is advisory. It should not directly command robot motion or close work orders without deterministic checks/operator confirmation.

## Acceptance Checklist

- `uv run pytest -q dimos/experimental/dogops` passes.
- `capture_image` still works without Gemini.
- `gemini_inspect_image` returns unavailable/skipped cleanly without `GEMINI_API_KEY`.
- With a mocked Gemini response, action execution stores a `gemini_vision_analysis` evidence row and JSON file.
- Baseline lookup prefers the same waypoint from a previous route run.
- Dashboard shows authored Gemini action and route-run analysis evidence.
- No test or log prints `GEMINI_API_KEY`.

## Open Questions

- Which Gemini model should be the default for demo speed/cost: `gemini-2.5-flash` or a newer configured model?
- Should `gemini_inspect_image` be one action after `capture_image`, or should the dashboard offer a combined "Capture + Gemini Inspect" convenience button later?
- What pose tolerance should be used for nearest-pose fallback if same-waypoint and target fallback are unavailable?
