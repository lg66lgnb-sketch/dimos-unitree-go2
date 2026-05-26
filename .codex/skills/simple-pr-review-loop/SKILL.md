---
name: simple-pr-review-loop
description: Iterate on a pull request or branch until the latest review finds no P0, P1, or P2 issues. Use when the user wants Codex to repeatedly review a PR, fix the current actionable findings, verify the repo, commit, push, and re-review without the deeper adversarial claim/spec analysis of deep-pr-review-loop.
---

# Simple PR Review Loop

## Overview

Use this skill to run a hardening loop on the current branch: review the live diff, fix the newest actionable P0/P1/P2 findings, verify the repo, push, then review again. Treat reviews as snapshots of the current branch state, not as permanent truth.

## Workflow

### 1. Establish the loop target

- Review `HEAD` against the intended base branch. Default to `origin/main` unless the user or repo context says otherwise.
- Start from the current branch state, not from prior review comments.
- Keep a short iteration counter. Stop after 5 iterations unless the user asks for more.

### 2. Run a fresh review pass

- Review the current diff and the current tree state.
- Focus on bugs, regressions, unsafe behavior, broken packaging, and missing verification for changed behavior.
- Ignore stale findings that no longer reproduce on the current branch.
- Classify findings by severity.

### 3. Decide whether to continue automatically

- If the latest pass finds any `P0`, `P1`, or `P2`, continue the loop automatically.
- Stop only when the latest pass finds no active `P0`, `P1`, or `P2`.
- If a `P2` would materially broaden scope or requires a product decision, stop and ask the user.

### 4. Fix only the newest actionable findings

- Fix the findings from the newest review pass before reviewing again.
- Do not keep re-fixing stale findings from older passes unless they still reproduce.
- Keep hard cutovers. Do not add compatibility layers, feature flags, or temporary fallback paths unless the user explicitly requests them.
- When a finding spans shared contracts and multiple apps, update the shared source of truth first, then wire dependents.

### 5. Verify after each fix pass

- Run the repo-required verification after behavior changes.
- Prefer the repo's standard commands first. If the repo says to run `npm test` and `npm run build`, run both.
- Add narrower repro commands when they validate the exact bug path more directly than the full suite.
- Do not claim a finding is fixed unless the changed path is actually exercised.

### 6. Commit and push each successful iteration

- Commit only after verification passes, unless the user explicitly accepts broken verification.
- Use a focused commit message for the current iteration.
- Push after each successful iteration so the PR reflects the newest fixes before the next review pass.

### 7. Repeat from a fresh review

- After push, run a new review against the live branch state.
- Continue until the stop condition is met.
- End with a concise summary: latest review result, verification run, pushed commit/PR state, and why the loop stopped.

## Subagents

- Use an `explorer` subagent for an independent review pass when parallel review will speed up the loop.
- Ask the explorer for concrete `P0/P1/P2` findings with file and line references only.
- Use `worker` subagents only for disjoint write scopes.
- Keep the critical-path integration, verification, and final re-review local.
- Do not leak the intended finding into a reviewer prompt. Give the subagent the diff or task, not your conclusion.

## Review discipline

- Review the current branch, not stale PR comments.
- Prefer findings over summaries.
- Treat `P0/P1/P2` as loop-blocking severities.
- Stop the loop immediately and ask the user if a finding conflicts with user-owned uncommitted changes or requires a risky product decision.

## Output style during the loop

- Give short progress updates while reviewing, fixing, verifying, pushing, and re-reviewing.
- Keep the final summary compact and outcome-focused.
- If the loop stops with unresolved findings, report only the remaining active findings from the latest review pass.
