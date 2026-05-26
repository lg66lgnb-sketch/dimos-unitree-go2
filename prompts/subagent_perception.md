# Perception subagent prompt

Read `AGENTS.md`, `SPEC.md`, `STATUS.md`, and `docs/FAILURE_MEMORY.md` first.

Own only:

```text
dimos/experimental/dogops/detector.py
dimos/experimental/dogops/observation_module.py
dimos/experimental/dogops/test_detector.py
```

Goal: read AprilTag 36h11 IDs robustly and feed DogOps observations.

Use existing DimOS patterns from `dimos/perception/fiducial/marker_tf_module.py`.

Success:

```bash
uv run dimos apriltag --ids '10,20,101-104' --size-mm 100 --family tag36h11 --out /tmp/dogops-tags.pdf
uv run pytest -q dimos/experimental/dogops/test_detector.py
```

If hardware image stream integration fails twice, add guided `simulated_tag_ids` fallback and document it.
