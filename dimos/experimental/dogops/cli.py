from __future__ import annotations

import argparse
from pathlib import Path
import time

from dimos.experimental.dogops.config_loader import (
    DEFAULT_MANIFEST,
    DEFAULT_MISSION,
    DEFAULT_POLICY,
    DEFAULT_SITE,
    load_dogops_config,
)
from dimos.experimental.dogops.dashboard import serve_dashboard
from dimos.experimental.dogops.dashboard_static import write_dashboard_html
from dimos.experimental.dogops.mapping import (
    add_point_of_interest,
    add_waypoint,
    build_simulated_site_map,
    simulate_poi_captures,
)
from dimos.experimental.dogops.mission_engine import run_offline_simulation
from dimos.experimental.dogops.models import NavAction, NavEvent
from dimos.experimental.dogops.nav_eval import summarize_nav_events
from dimos.experimental.dogops.report import render_report_markdown
from dimos.experimental.dogops.rerun_sim import DEFAULT_RERUN_SOURCE_URL, serve_rerun_sim
from dimos.experimental.dogops.store import DogOpsStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dogops", description="DogOps offline CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate DogOps YAML configs")
    _add_config_args(validate)

    start = subparsers.add_parser("start", help="Create an empty operator demo run")
    _add_config_args(start)
    start.add_argument("--out", default=".dogops/runs/latest")

    simulate = subparsers.add_parser("simulate", help="Run the offline DogOps mission")
    _add_config_args(simulate)
    simulate.add_argument("--out", default=".dogops/runs/latest")

    report = subparsers.add_parser("report", help="Regenerate a report from a run directory")
    report.add_argument("--run", default=".dogops/runs/latest")
    report.add_argument("--out", default=None)

    map_cmd = subparsers.add_parser("map", help="Generate or refresh the local open-space map")
    map_cmd.add_argument("--run", default=".dogops/runs/latest")

    plan = subparsers.add_parser("plan", help="Edit route waypoints and photo points")
    plan.add_argument("--run", default=".dogops/runs/latest")
    plan.add_argument("--add-waypoint", action="append", default=[])
    plan.add_argument("--add-poi", action="append", default=[])

    run_plan = subparsers.add_parser("run-plan", help="Simulate the route and POI captures")
    run_plan.add_argument("--run", default=".dogops/runs/latest")

    serve = subparsers.add_parser("serve", help="Serve a local dashboard for a run directory")
    serve.add_argument("--run", default=".dogops/runs/latest")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

    rerun_sim = subparsers.add_parser(
        "rerun-sim",
        help="Publish the DogOps simulator map/route/POI state to a local Rerun stream",
    )
    rerun_sim.add_argument("--run", default=".dogops/runs/latest")
    rerun_sim.add_argument("--source-url", default=DEFAULT_RERUN_SOURCE_URL)
    rerun_sim.add_argument("--poll-interval-s", type=float, default=0.5)
    rerun_sim.add_argument(
        "--view-mode",
        choices=["dogops-2d", "native-3d"],
        default="dogops-2d",
        help=(
            "dogops-2d publishes the lightweight fallback map; native-3d overlays "
            "DogOps route/POI labels onto an existing DimOS Go2 Rerun stream and "
            "fails if that native stream is not running"
        ),
    )

    return parser


def _add_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--site", default=str(DEFAULT_SITE))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--mission", default=str(DEFAULT_MISSION))
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate":
        config = load_dogops_config(args.site, args.manifest, args.mission, args.policy)
        print(
            "validated "
            f"site={config.site.site_id} "
            f"manifest={config.manifest.manifest_id} "
            f"mission={config.mission.mission_id}"
        )
        return 0

    if args.command == "start":
        config = load_dogops_config(args.site, args.manifest, args.mission, args.policy)
        store = DogOpsStore(
            args.out,
            site=config.site,
            manifest=config.manifest,
            policy=config.policy,
            mission=config.mission,
        )
        run = store.create_run(config.mission.mission_id, started_at=time.time())
        state = store.state
        assert state is not None
        store.set_site_map(state.site_map)
        store.set_route_plan(state.route_plan)
        store.write_report(run.id)
        write_dashboard_html(args.out)
        print(f"run_id={run.id}")
        print(f"state={getattr(run.state, 'value', run.state)}")
        print(f"dashboard={Path(args.out) / 'dashboard.html'}")
        return 0

    if args.command == "simulate":
        state = run_offline_simulation(
            site=args.site,
            manifest=args.manifest,
            mission=args.mission,
            policy=args.policy,
            out=args.out,
        )
        print(f"run_id={state.run.id}")
        print(f"state={getattr(state.run.state, 'value', state.run.state)}")
        print(f"report={Path(args.out) / 'report.md'}")
        return 0

    if args.command == "report":
        store = DogOpsStore.load_existing(args.run)
        state = store.state
        assert state is not None
        content = render_report_markdown(state)
        out_path = Path(args.out) if args.out else Path(args.run) / "report.md"
        out_path.write_text(content, encoding="utf-8")
        store.write_report(state.run.id)
        print(f"report={out_path}")
        return 0

    if args.command == "map":
        store = DogOpsStore.load_existing(args.run)
        state = store.state
        assert state is not None
        site_map = build_simulated_site_map(state.site, state.nav_events)
        store.set_site_map(site_map)
        store.write_state(state.run.id)
        store.write_report(state.run.id)
        print(f"map={Path(args.run) / 'map.json'}")
        print(f"coverage={site_map.coverage_ratio:.2f}")
        return 0

    if args.command == "plan":
        store = DogOpsStore.load_existing(args.run)
        state = store.state
        assert state is not None
        for target_id in args.add_waypoint:
            add_waypoint(state.route_plan, state.site, target_id)
        for target_id in args.add_poi:
            add_point_of_interest(state.route_plan, state.site, target_id)
        store.set_route_plan(state.route_plan)
        store.write_state(state.run.id)
        store.write_report(state.run.id)
        print(f"route_plan={Path(args.run) / 'route_plan.json'}")
        print(f"waypoints={len(state.route_plan.waypoints)}")
        print(f"points_of_interest={len(state.route_plan.points_of_interest)}")
        return 0

    if args.command == "run-plan":
        store = DogOpsStore.load_existing(args.run)
        state = store.state
        assert state is not None
        next_nav_index = len(state.nav_events) + 1
        for offset, waypoint in enumerate(state.route_plan.waypoints):
            store.append_nav_event(
                NavEvent(
                    id=f"NAV-{next_nav_index + offset:03d}",
                    run_id=state.run.id,
                    ts=time.time(),
                    action=NavAction.goto,
                    target_id=waypoint.target_id,
                    success=True,
                    elapsed_s=3.0 + (offset * 0.5),
                    note="operator route simulation",
                )
            )
        state.nav_summary = summarize_nav_events(state.run.id, state.nav_events)
        site_map = build_simulated_site_map(state.site, state.nav_events)
        store.set_site_map(site_map)
        captures, readings = simulate_poi_captures(
            run_id=state.run.id,
            plan=state.route_plan,
            evidence_dir=Path(args.run) / "evidence",
        )
        store.replace_poi_results(captures, readings)
        store.write_state(state.run.id)
        store.write_report(state.run.id)
        print(f"captures={len(captures)}")
        print(f"readings={len(readings)}")
        return 0

    if args.command == "serve":
        serve_dashboard(args.run, host=args.host, port=args.port)
        return 0

    if args.command == "rerun-sim":
        serve_rerun_sim(
            args.run,
            source_url=args.source_url,
            poll_interval_s=args.poll_interval_s,
            view_mode=args.view_mode,
        )
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
