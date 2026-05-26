# DimOS integration subagent prompt

Read `AGENTS.md`, `SPEC.md`, `STATUS.md`, and `docs/FAILURE_MEMORY.md` first.

Own only:

```text
dimos/experimental/dogops/skills.py
dimos/experimental/dogops/blueprints.py
dimos/robot/unitree/go2/blueprints/agentic/unitree_go2_dogops.py
dimos/robot/all_blueprints.py
```

Goal: expose DogOps through DimOS/MCP without API keys.

Rules:

- Base `unitree_go2_dogops` must not include `McpClient`.
- It may include `McpServer`.
- Optional `unitree_go2_dogops_agentic` may include `McpClient` only after base works.
- DogOps modules used in the blueprint should tolerate framework-injected kwargs such as `g=`.
- The Go2 blueprint file should expose a real module-level `unitree_go2_dogops`; fallback metadata is only for isolated import tests.

Success:

```bash
uv run pytest -q dimos/experimental/dogops
CI=1 uv run pytest -q -o addopts='' dimos/robot/test_all_blueprints_generation.py || true
CI=1 uv run pytest -q -o addopts='' dimos/robot/test_all_blueprints_generation.py
uv run dimos list | rg dogops
uv run dimos mcp list-tools | rg 'run_mission|scan_zone|verify_work_order|nav_eval_report'
```

If replay deploys modules but `dimos status` or MCP discovery cannot see a running instance, document in failure memory and leave direct skill tests working.

Do this before demo polish. A local CLI-only fallback is not final unless the full DimOS blocker is documented.
