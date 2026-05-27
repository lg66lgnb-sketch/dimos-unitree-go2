# AGENTS.md

## Sources of truth
- Read `SPEC.md` before planning or editing; it is canonical.
- For backlog/roadmap work, also read `STATUS.md`; update it when backlog state changes.
- Do not contradict `SPEC.md`. If product direction changes, update `SPEC.md` first.
- Keep this file short. Add rules only after real repeated mistakes; prune stale rules.
- Assume the real Unitree Go2 is available and the final target is the full DimOS checkout on the Mac.

## Commands and tools
- Discover project commands from `package.json`, `Makefile`, `README.md`, `SPEC.md`, or existing scripts before guessing.
- Use existing project tools/package manager; do not add new tooling or dependencies unless requested.
- Prefer `rg`, `fd`, `jq`, `git`, `gh`, `curl`, and project CLIs before MCPs.
- Prefer targeted checks while iterating; before handoff run the relevant full checks: lint, typecheck, tests, build.
- For UI changes, verify visually with before/after screenshots when practical.

## Working rules
- For non-trivial changes, state verifiable success criteria before writing code.
- Make surgical diffs. Every changed line must trace to the request.
- Prefer deleting code over adding code when deletion fully solves the problem.
- Use hard cutover for product changes: remove replaced paths instead of leaving stale parallel UI.
- Prefer running code over guessing. Read full errors, logs, and stack traces before editing.
- After two failed fixes for the same issue, stop and summarize facts learned before changing strategy.
- Validate DimOS registry/MCP early. Do not leave `dimos list | rg dogops` until final polish.
- Use `$DIMOS_ROOT` / `DOGOPS_DIMOS_ROOT` for full-DimOS validation; never hard-code a contributor's local DimOS path in product code or docs.
- For real-Go2 runs, keep speed/route conservative, verify `unitree-go2` before `unitree-go2-dogops`, and always run/know `uv run dimos stop --force`.

## Git and GitHub
- Default to a dedicated git worktree for each non-trivial Codex thread. Do not work on a branch already used by another active thread.
- Never commit or push directly to `main`/`master`; use a task branch in an isolated worktree.
- At task start run: `git status -sb`, `git fetch --prune origin`, `git branch --show-current`, and `gh auth status`.
- Do not switch branches, pull, rebase, reset, stash, or discard local changes unless needed and safe.
- When creating a task branch, base it on the current remote default branch.
- Before committing, inspect `git diff` and commit only relevant files.
- Before pushing, fetch again, verify branch/account, and push only the current task branch.
- Open draft PRs for non-trivial work; include summary, checks run, failures, and risks.
- Clean up local worktrees after their branch is merged or no longer needed: confirm they are clean, remove with `git worktree remove <path>`, then prune stale metadata. Never remove a worktree that has uncommitted or unpushed work.
- Never force-push shared branches. If explicitly needed on your own branch, use `--force-with-lease`.
- Do not add `Co-Authored-By` unless explicitly requested.

## Security and privacy
- Never commit secrets or sensitive local artifacts: `.env`, keys, tokens, mnemonics, wallets, keystores, local DBs, secret-bearing logs, private maps, device IDs, personal paths/names, or sensitive screenshots.
- Never expose server secrets through browser/Vite public variables.
- Hosted write APIs must be server-only, admin-token protected, allowlisted, idempotent where possible, and testnet-only.
- The base demo must run without cloud secrets. Optional AI/cloud features must degrade cleanly.
- Treat upstream DimOS PRs/issues as research targets; do not make the base demo depend on unmerged upstream work.

## Parallel work
- Use subagents/worktrees only for separable work.
- Assign explicit files or areas before edits; avoid concurrent edits to the same file.
- Each subagent must read `SPEC.md`, this file, and `STATUS.md` if backlog-related.
- Each subagent must report changed files, checks run, failures, and remaining risks.
- Merge only after the main worktree passes the relevant checks.

## Failure memory
- Record repeated failures in `docs/FAILURE_MEMORY.md` before changing strategy.
- Do not retry the same failing approach more than twice without a new fact.
