# UPSTREAM_WORKFLOW.md

## Goal

DogOps should live in a public repo and may require changes to upstream DimOS. Keep hackathon work fast while preserving a path to clean upstream PRs.

## Recommended branch layout

```bash
git remote -v
git remote add upstream https://github.com/dimensionalOS/dimos.git || true
git fetch upstream main
git checkout -b dogops/siteops-agent upstream/main
```

Use focused commits:

```text
dogops: add offline mission engine
dogops: add report and dashboard
dogops: expose siteops mcp skills
dogops: add go2 blueprint
dogops: add apriltag observation module
dogops: add demo docs and configs
```

## Worktrees for subagents

Use worktrees only when broad exploration would flood the main context.

```bash
cd ~/code/dimos
git worktree add ../dimos-dogops-core -b dogops/core
git worktree add ../dimos-dogops-dashboard -b dogops/dashboard
git worktree add ../dimos-dogops-dimos -b dogops/dimos-integration
```

Rules:

- Each worktree/subagent owns explicit files.
- Avoid concurrent edits to the same file.
- Merge back after tests pass.
- Resolve conflicts manually; do not let Codex invent parallel code to avoid conflicts.

## When to modify upstream core

Prefer `dimos/experimental/dogops` for product code.

Modify core DimOS only when:

- an existing module has a real bug that blocks DogOps;
- the fix is generic and tested;
- the fix does not require DogOps-specific assumptions.

Examples of acceptable upstream fixes:

- CLI command bug;
- marker detector bug;
- blueprint registry/import issue;
- safe doc correction;
- small compatibility fix.

Examples to avoid in upstream core:

- DogOps business rules;
- demo-specific config;
- one-off hacks for Go2 camera visibility;
- cloud API assumptions.

## PR split after hackathon

If submitting upstream PRs, split them:

1. Generic DimOS fixes.
2. DogOps experimental product/demo.
3. Docs/configs/demo assets.

## Privacy and public repo

Never commit:

- `.env`;
- API keys/tokens;
- robot serials/device IDs;
- private venue map;
- logs with personal data;
- screenshots of private dashboards;
- local absolute paths;
- generated `.dogops/runs/*` unless deliberately added as tiny anonymized fixtures.

Add this to `.gitignore` if missing:

```gitignore
.dogops/
*.local.yaml
*.private.yaml
.env
.env.*
```

## Keeping in sync with upstream

```bash
git fetch upstream main
git rebase upstream/main
# or, if time is short and conflicts are risky:
git merge upstream/main
```

During hackathon, prioritize a working demo over perfect rebases.
