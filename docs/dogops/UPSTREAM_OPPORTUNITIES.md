# Upstream DimOS Opportunities

Scope: public GitHub state for `dimensionalOS/dimos`, focused on DogOps / SiteOps usefulness.

## Decision

Use upstream work, but do not make the hackathon demo depend on unmerged navigation PRs.

DogOps must have a stable offline/core path first:

1. deterministic mission engine;
2. manifest + site policy;
3. AprilTag/package/asset observations;
4. work-order lifecycle;
5. dashboard/report;
6. navigation metrics.

After that, use upstream PRs as optional accelerators and goodwill contributions.

## Use Codex or GPT?

Use GPT for strategy and written triage. Use Codex for local validation.

Codex should run in the Mac/full DimOS checkout because the real Go2 is available and final registry/hardware validation must happen there. Use the Ubuntu VM only for isolated offline PR experiments.

Codex can:

- `gh pr checkout` branches;
- run `uv` test loops;
- inspect diffs with `rg`, `git diff`, and `pytest`;
- create small focused patches;
- record failures in `STATUS.md` and this file.

Do not ask Codex to make strategic project-direction calls. Give it the selected PR/issue and success criteria.

## Safety rule for upstream branches

Never base the main DogOps demo branch on a draft or unmerged navigation PR.

Use worktrees:

```bash
git fetch origin
git worktree add ../dimos-dogops main
cd ../dimos-dogops

# For each PR under test:
git fetch origin pull/2236/head:pr-2236
git worktree add ../dimos-pr-2236 pr-2236
```

Prefer `gh` if available:

```bash
gh pr checkout 2236
uv run pytest -q <narrow tests>
```

If a PR fails twice for the same reason, stop and write the failure under `Failure memory`.

## Ranked upstream opportunities

### Recently validated: PR #2245 — SHM transports for Go2 replay / macOS

URL: https://github.com/dimensionalOS/dimos/pull/2245
Status seen: open.
Validation reference: compare current DimOS `main` against the PR branch in disposable local checkouts.

Why it matters: macOS is sensitive to high-bandwidth DimOS streams over LCM/UDP. DogOps will likely need reliable Go2 camera, lidar, point cloud, map, and costmap visualization during replay/sim/hardware dry runs.

What the comparison showed:

- Current `main` visible Go2 sim reached `RerunWebSocketServer: viewer connected` and `MuJoCo process started successfully`.
- PR #2245 visible Go2 sim reached the same milestones after first-run LFS/model downloads.
- Current `main` routes only `color_image` through `pSHMTransport`.
- PR #2245 routes `color_image`, `pointcloud`, `lidar`, `global_map`, `merged_map`, `global_costmap`, and `navigation_costmap` through `pSHMTransport`.
- PR #2245 focused blueprint/CLI tests passed: `22 passed`.
- A broader lean local test run was not fully clean: `51 passed`, `1 failed`, `5 errors`. The errors were missing local test tooling (`pytest-mock`); the failure was `dimos/core/test_core.py::test_basic_deployment` with zero movement messages.

DogOps decision: track this PR as a likely Mac reliability improvement, but do not make the base demo depend on it while it is unmerged. Adopt after merge, or cherry-pick only if DogOps replay/visual streams drop on macOS and a focused DogOps smoke test proves the PR fixes it.

Still required on macOS: local `.venv`, `git-lfs`, `portaudio`, the MuJoCo `libpython3.12.dylib` venv symlink workaround, and cautious handling of DimOS host configurators for real robot runs.

### 1. PR #2236 — Clean Go2 Static Transform frames

URL: https://github.com/dimensionalOS/dimos/pull/2236
Status seen: open.
Branch seen: `jeff/fix/go2_tf`.
Why it matters: DogOps depends on camera/tag/asset observations being spatially meaningful. Cleaner Go2 static transforms can improve AprilTag-to-base-frame reasoning and Rerun visualization.

Use for DogOps: high.
Risk: medium-low.
Depend on it for base demo: no.
Best contribution: run replay + Go2 Air validation, check camera/tag frame names, report screenshots/logs, and fix narrow issues if found.

Codex validation:

```bash
gh pr checkout 2236
uv run dimos --replay run unitree-go2
uv run pytest -q dimos/robot/test_all_blueprints.py
```

Exit path: if replay imports fail or dependencies explode, record logs and keep DogOps tags in local camera/image coordinates with explicit caveat.

### 2. Issue #1634 — Investigate potential Go2 performance issues

URL: https://github.com/dimensionalOS/dimos/issues/1634
Status seen: open.
Why it matters: DogOps needs repeatable Go2 replay/hardware performance. The issue asks for timing `dimos --replay --viewer=none run unitree-go2` on current and older dev states.

Use for DogOps: high.
Risk: low.
Depend on it for base demo: no.
Best contribution: produce a simple benchmark table from a Linux VM and macOS host, then comment/open PR if a regression is found.

Codex validation:

```bash
/usr/bin/time -p uv run dimos --replay --viewer=none run unitree-go2
/usr/bin/time -v uv run dimos --replay --viewer=none run unitree-go2 2>&1 | tee .dogops/go2_replay_time.txt
```

Exit path: if replay cannot run, record exact install/runtime blocker; still keep DogOps offline simulator.

### 3. PR #2138 — Go2 Speed vs Precision testing

URL: https://github.com/dimensionalOS/dimos/pull/2138
Status seen: draft.
Branch seen: `mustafa/task/go2-controller-tuning`.
Why it matters: It is close to DogOps NavEval. It proposes Go2 characterization and benchmarking artifacts that answer: for a tolerance, what speed is safe?

Use for DogOps: medium-high.
Risk: medium.
Depend on it for base demo: no.
Best contribution: salvage the benchmark concepts into DogOps `nav_eval.py`; optionally help upstream by fixing narrow CI blockers.

Known blockers seen:

- missing `git-lfs` in CI path;
- project `test_no_sections` violations from section-style comments.

Codex validation:

```bash
gh pr checkout 2138
uv run pytest dimos/utils/benchmarking/test_tuning.py -q
uv run python -m dimos.utils.benchmarking.characterization --mode self-test
uv run python -m dimos.utils.benchmarking.benchmark --config <artifact> --mode sim --speeds 0.5
```

Exit path: if branch is too broad, do not merge. Implement DogOps-only metrics: waypoint attempted/reached, retry count, tag reacquisition time, route duration, operator intervention count.

### 4. PR #2234 — MCP parallel tool dispatch with per-lane locks

URL: https://github.com/dimensionalOS/dimos/pull/2234
Status seen: open.
Branch seen: `johnny-kantaros:jkantaros/parallelToolCalling`.
Why it matters: Agent workflows benefit when observation/reporting can run while motion-lane tools remain serialized.

Use for DogOps: medium.
Risk: medium.
Depend on it for base demo: no; base demo has no API-key dependency.
Best contribution: validate tests and, if merged, annotate DogOps skills with safe lanes.

Codex validation:

```bash
gh pr checkout 2234
uv run pytest dimos/agents/mcp/test_mcp_client_unit.py dimos/agents/mcp/test_mcp_server.py -v
```

DogOps lane policy if available:

- `motion`: movement/nav commands;
- `observe`: read camera/tag/package state;
- `state`: mutate incidents/work orders;
- no lane: pure reporting/formatting.

Exit path: if PR is not merged, DogOps skills remain synchronous and deterministic.

### 5. PR #2241 — Dimos map tool

URL: https://github.com/dimensionalOS/dimos/pull/2241
Status seen: open.
Branch seen: `feat/ivan/maptool`.
Why it matters: Adds `dimos map` tooling to visualize memory2 maps, raw/PGO-corrected maps, and export corrected maps.

Use for DogOps: medium.
Risk: medium-high.
Depend on it for base demo: no.
Best contribution: if branch is current, validate map command on replay database; otherwise use DogOps dashboard map pins instead.

Codex validation:

```bash
gh pr checkout 2241
uv run dimos map --help
# Then test on available memory2/replay DB only if data exists.
```

Exit path: if memory2 data or gtsam dependencies block it, use local 2D arena map in DogOps dashboard.

### 6. PR #2242 — Loop closure / map reconstruction first pass

URL: https://github.com/dimensionalOS/dimos/pull/2242
Status seen: open.
Branch seen: `feat/ivan/pgo_rewrite`.
Why it matters: Rewrites PGO drift correction into composable streams and adds richer map visualization / loop closure overlays.

Use for DogOps: medium.
Risk: high.
Depend on it for base demo: no.
Best contribution: do not try to merge wholesale during the hackathon. If helping upstream, target the specific review issues.

Known review issues seen:

- `PointCloud2.transform()` may strip color/intensity;
- zero-translation pose normalization can fail when `Vector3(0,0,0)` is falsy;
- duplicate/dead return block in PGO internals;
- possible keyframe filtering issue;
- origin-cell truncation concern.

Codex validation:

```bash
gh pr checkout 2242
uv run pytest -q dimos/mapping/relocalization/test_pgo.py
uv run pytest -q dimos/msgs/sensor_msgs/test_PointCloud2.py dimos/memory2/type/test_observation.py
```

Exit path: only cherry-pick small safe fixes into a separate upstream PR. Never block DogOps on PGO.

### 7. PR #2237 — PointCloud2 including time per point

URL: https://github.com/dimensionalOS/dimos/pull/2237
Status seen: open.
Branch seen: `LuigiVan01:feature/pointcloud2-time-per-point`.
Why it matters: Per-point timestamps help motion-deskew consumers such as FAST-LIO. This is useful if DogOps later leans into SLAM/LiDAR, but not required for the 90-second demo.

Use for DogOps: low-medium.
Risk: low.
Depend on it for base demo: no.
Best contribution: add the missing XYZRGB+times round-trip test and make the time-field offset derive from current point step rather than hardcoding 16.

Codex validation:

```bash
gh pr checkout 2237
uv run pytest dimos/msgs/sensor_msgs/test_PointCloud2.py -q
```

Exit path: skip if DogOps does not use point-cloud timing.

### 8. PR #2188 — memory2 Space raster backend + experimental memory2 agent

URL: https://github.com/dimensionalOS/dimos/pull/2188
Status seen: open.
Branch seen: `Mgczacki:memory2-vis-and-agent`.
Why it matters: It directly targets spatial representations that LLMs/agents can reason about. It adds `Space.to_bgr()` / `Space.to_png()`, visual overlays, and an experimental memory2 agent.

Use for DogOps: conceptual high, implementation medium.
Risk: high.
Depend on it for base demo: no.
Best contribution: borrow product ideas and, if feasible, make DogOps report/dashboard export a top-down annotated raster that addresses Issue #1913.

Codex validation:

```bash
gh pr checkout 2188
uv run pytest -q dimos/memory2
```

Exit path: DogOps dashboard uses its own simple HTML/SVG/PNG map if memory2 raster is not ready.

### 9. Issue #1913 — Investigate agentic understanding of space

URL: https://github.com/dimensionalOS/dimos/issues/1913
Status seen: open.
Why it matters: DogOps can contribute a small benchmark: can an agent answer spatial questions from an annotated facility map and incident history?

Use for DogOps: medium-high.
Risk: low if deterministic; high if VLM-dependent.
Depend on it for base demo: no.
Best contribution: add `dogops spatial-eval` with ground-truth questions about rooms/zones/packages/incidents.

Suggested DogOps eval questions:

- Which package is blocking cooling?
- Which zone has an unresolved P1 issue?
- Which inspected asset changed since baseline?
- Which waypoint had recovery retries?
- What should be inspected next?

Exit path: implement deterministic scoring first; optional LLM/VLM later.

### 10. PR #2143 and merged PR #2160 — Relocalization spec / Go2 relocalization

URLs:

- https://github.com/dimensionalOS/dimos/pull/2143
- https://github.com/dimensionalOS/dimos/pull/2160

Status seen:

- #2143 draft;
- #2160 merged on 2026-05-23.

Why it matters: Relocalization is directly aligned with the Autonomy track. #2160 mentions loaded maps, `map -> world` transform, costmapper support, pre-map export CLI, and AprilTag detection later.

Use for DogOps: medium.
Risk: medium.
Depend on it for base demo: no.
Best contribution: DogOps can fill the AprilTag eval gap: tag-based relocalization checkpoints, route drift markers, and dashboard metrics.

Exit path: use static arena coordinates and tag IDs; do not promise full relocalization if live map loading is unstable.

### 11. PR #2137 — Autoresearch on relocalization

URL: https://github.com/dimensionalOS/dimos/pull/2137
Status seen: draft.
Branch seen: `sloptimization/ransac`.
Why it matters: It reports sub-1s CPU alignment from 5s of LiDAR data and explores confidence measures for relocalization.

Use for DogOps: research only.
Risk: high.
Depend on it for base demo: no.
Best contribution: borrow the concept of confidence metrics; do not integrate broad branch.

Exit path: tag reacquisition confidence and waypoint success are enough for DogOps demo.

### 12. PR #2213 — `dimos graph` subcommand

URL: https://github.com/dimensionalOS/dimos/pull/2213
Status seen: open.
Branch seen: `jeff/feat/dimos-graph`.
Why it matters: Could visualize the DogOps blueprint in a browser, which helps product polish and judging.

Use for DogOps: low-medium.
Risk: medium.
Depend on it for base demo: no.
Known issue seen: relative imports can fail when blueprint files are loaded with `spec_from_file_location`.
Best contribution: fix package-context loading and add tests.

Exit path: DogOps README can include its own architecture Mermaid diagram.

### 13. PR #2195 — MCP client image LangGraph command

URL: https://github.com/dimensionalOS/dimos/pull/2195
Status seen: open.
Branch seen: `mcp-client-image-langgraph-command`.
Why it matters: Helps agents receive image tool results in the same turn, useful for VLM/visual inspection.

Use for DogOps: optional.
Risk: medium.
Depend on it for base demo: no, because the base product avoids API-key requirements.
Best contribution: only test if DogOps adds Gemini/OpenAI image narration.

Exit path: keep image evidence in dashboard/report, not LLM context.

## What I did not find

I did not find a high-signal open PR specifically for shipping/receiving or warehouse inspection. DogOps should own that product layer.

## Recommended upstream sequence

Do these in order after DogOps Part A/B is working.

### Day 0 / setup

1. Install GitHub CLI and git-lfs in Ubuntu VM.
2. Run baseline replay timing for Issue #1634.
3. Save logs in `.dogops/upstream/`.

### Day 1 / high-confidence upstream work

1. Validate PR #2236 Go2 transform cleanup.
2. If it helps AprilTag spatialization, use or mention it in DogOps demo notes.
3. Comment upstream with Go2 Air / replay results if useful.

### Day 1-2 / DogOps NavEval

1. Implement DogOps-only `nav_eval.py` independent of upstream PRs.
2. Borrow concepts from PR #2138 but not the broad branch.
3. Dashboard must show route metrics and recovery count.

### Optional goodwill PRs

Pick at most one:

- Fix PR #2237 test/offset gap.
- Fix PR #2213 relative import loading.
- Help PR #2242 with the zero-vector or PointCloud2 color regression.

Do not attempt all three before the hackathon.

## Codex prompt: upstream triage

Paste this after the DogOps core simulation passes:

```text
Read SPEC.md, STATUS.md, and docs/dogops/UPSTREAM_OPPORTUNITIES.md.

Goal: validate useful DimOS upstream PRs/issues without destabilizing DogOps.

Rules:
- Do not change DogOps product direction.
- Do not base DogOps main branch on draft/unmerged PRs.
- Use git worktrees or `gh pr checkout` in isolated branches.
- After two failed fixes on the same PR, stop and record logs in STATUS.md and docs/dogops/UPSTREAM_OPPORTUNITIES.md.
- Prefer narrow tests and concrete logs.

Phase 1:
- Run baseline Go2 replay timing for issue #1634.
- Save command, stdout/stderr, wall/user/sys time.

Phase 2:
- Check out PR #2236.
- Run its stated replay check and relevant blueprint tests.
- Decide whether DogOps should use it, ignore it, or only reference it.

Phase 3:
- Check PR #2138 only for ideas/tests.
- Do not merge it into DogOps.
- Implement DogOps nav_eval metrics independently if needed.

Phase 4:
- Pick exactly one small upstream goodwill task from #2237, #2213, or #2242.
- Make a surgical fix in a separate branch.
- Run narrow tests.
- If clean, prepare a PR description.

Deliverables:
- `.dogops/upstream/baseline_go2_timing.md`
- `.dogops/upstream/pr_2236_validation.md`
- updated STATUS.md
- no demo-breaking dependency on upstream PR branches
```

## Failure memory

Add failures here in this format:

```text
### YYYY-MM-DD — PR/issue — summary
Command:
Observed:
Tried:
Decision:
Next safe path:
```
