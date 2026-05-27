---
name: deep-pr-review-loop
description: Deep adversarial pull request review and fix loop. Use when the user asks for a deeper PR review, adversarial review, review loop including P2s, subagent review, claim/spec validation, test adequacy review, or when prior normal review missed issues. Reviews the live PR/branch against its base, challenges every behavior claim for reachability and adjacent-contract regressions, uses parallel read-only review lenses when available, fixes actionable P0/P1/P2 findings when the user asked to fix, verifies with targeted and repo tests, commits, pushes, and repeats until no active P0/P1/P2 remain.
---

# Deep PR Review Loop

## Overview

Use this skill as an adversarial review-fix loop for the current PR or branch. Each iteration searches for active P0/P1/P2 issues, fixes the newest actionable findings when the user asked for fixes, verifies the changed behavior, commits and pushes after successful verification, then starts a fresh review against the new head. Continue until the latest review finds no active P0/P1/P2 issues, or until blocked by a product decision, user-owned changes, unavailable verification, or the 5-iteration safety limit.

Review the current PR or branch adversarially, not just the changed lines. Treat the PR title/body, user claims, changed tests, and changed code as claims that must be proven by reachable behavior and adequate tests.

This review must explicitly check **route equivalence** and **state-substate behavior**. If one user intent can enter through multiple paths, such as structured actions, typed/natural-language text, resume/replay, signed-in recovery, or feature-disabled fallbacks, compare those paths directly. If an object has nested status or expiry fields, such as a parent quote plus method-specific payment terms, test parent-only, child-only, both-live, and both-expired states.

Default to including P2 findings as loop-blocking unless the user explicitly asks for P0/P1 only.

## Workflow

### 1. Establish The Target

- Identify the PR or branch and intended base. Default to `origin/main` unless repo context says otherwise.
- Inspect PR title/body, linked user request, current diff, changed files, live review comments, and CI status.
- Start from current branch state. Ignore stale findings unless they still reproduce.
- Keep an iteration counter and stop after 5 iterations unless the user asks for more.

### 2. Extract Review Claims

Before reviewing code, write down the PR's concrete behavior claims from:

- PR title/body and commit messages.
- Changed user-facing copy.
- Added/updated tests.
- Changed function names, constants, schemas, route handlers, and validation helpers.
- Review comments or user feedback that motivated the PR.

For each claim, ask:

- What observable behavior should change?
- Which code path makes that behavior reachable?
- Which other ingress paths express the same user intent, and do they use the same handler or a different handler?
- Does any cleanup, sanitization, normalization, pruning, or cache refresh run before the branch that decides behavior?
- Does the changed object have nested state, expiry, or availability fields whose lifecycle can diverge from the parent object?
- Which adjacent helpers, shared contracts, state machines, stores, validators, or UI flows must still agree?
- Which test would fail if the claim were false?

Create a small route/state matrix for every launch-relevant claim:

- **Ingress paths:** structured action, typed text, assistant/tool replay, resume/recovery, signed-in vs signed-out, feature enabled vs unavailable.
- **State variants:** parent live/expired, child or method live/expired, sanitized/restored, cached/stale, duplicate/retry, missing source context.
- **Expected behavior:** refresh, reject, ask for disambiguation, execute action, or no-op.
- **Current tests:** exact test names that pin each row, or a written reason the row is equivalent and does not need its own test.

### 3. Run Parallel Read-Only Review Lenses

Spawn independent `explorer` subagents for these lenses before concluding a deep review. If subagents are unavailable in a future runtime, explicitly say so and perform the same lenses locally. Keep prompts neutral and do not leak suspected findings.

- **Code quality and maintainability:** bugs, dead code, duplicated fragile contracts, unsafe data flow, stale comments, packaging/build risks.
- **Spec/product compliance:** whether implementation matches PR claims, repo contracts, user workflow, edge cases, adjacent helper behavior, and equivalent user intents that enter through different handlers.
- **Test adequacy and execution:** missing branch coverage, weak assertions, untested new helpers, green tests that do not prove the claim, and route/state matrix rows without direct or defensible coverage.

Ask each reviewer for concrete P0/P1/P2 findings with file and line references only. While they run, perform your own local review. Synthesize results; do not blindly accept subagent findings without checking whether they reproduce in current code.

### 4. Adversarial Local Review Checklist

Apply this checklist on every fresh pass:

- **Reachability:** Verify every changed helper is actually called by the claimed flow. If a changed function is unused, either remove it or wire it with tests.
- **Ingress/route equivalence:** For every supported user intent, compare structured actions, typed/natural-language text, assistant/tool replay, resume/recovery, signed-in state, and feature availability. If different handlers are used, verify they preserve the same pre-cleanup state signals and produce equivalent behavior where product expects equivalence.
- **State-substate matrix:** If behavior depends on an object with nested state, expiry, or availability, test or reason through parent-only expiry, child-only expiry, both live, both expired, sanitized/restored, and missing-source cases. Do not let a parent-expiry test stand in for a method-specific or child-expiry test.
- **Mutation-before-decision audit:** Identify cleanup, sanitization, normalization, pruning, cache refresh, or field deletion that happens before routing/availability decisions. Ask whether that mutation removes evidence a later branch needs, especially expired nested fields or privacy context.
- **Adjacent contracts:** Inspect nearby helpers and shared types, not only diff hunks. State machines, validators, stores, persistence, analytics, and UI resume/retry paths often hold the real bug.
- **Country/state/locale/generalization:** If a PR broadens behavior, test a representative non-default case. Do not assume US/default behavior proves international behavior.
- **Intent/routing collisions:** For regex or classifier changes, test both positive prompts and product/ordinary-language collisions.
- **Duplicate strings and copy contracts:** If server and client duplicate user-facing copy used for suppression, parsing, or matching, flag drift risk or add tests.
- **Error and retry paths:** Review fallback, timeout, validation-failure, duplicate-submit, and resume paths. These are commonly missed by happy-path tests.
- **Security and privacy:** Check that new persistence, analytics, logs, SSE events, and UI payloads do not expose secrets, PII, or internal tokens.
- **Test strength:** Prefer tests that fail on the exact regression, not broad smoke tests. Confirm each changed branch has either direct coverage or a defensible reason not to.
- **Equivalence tests:** If the PR fixes a behavior for one route, add at least one regression for any materially distinct equivalent route, or document why the routes share the same handler after the fix.

### 5. Severity Rules

- `P0`: data loss, security breach, production-wide outage, irreversible unsafe action.
- `P1`: likely user-facing breakage, payment/order safety issue, privacy leak, failing required workflow, or claim-breaking bug.
- `P2`: real but narrower bug, missing test for meaningful new behavior, dead code in claimed behavior, maintainability issue likely to cause drift, accessibility/UX flaw with practical impact.
- Do not report style-only preferences as P2 unless they create concrete risk.

If the user requested a read-only review, stop after findings and say what you would do. Do not edit files.

### 6. Fix The Newest Actionable Findings

When the user wants fixes:

- Fix only active findings from the newest pass.
- Keep changes scoped to the PR branch. Avoid unrelated refactors.
- If a finding spans shared contracts and multiple apps, update the shared source of truth first, then dependents.
- Do not add feature flags, compatibility layers, or temporary fallback paths unless the user explicitly asks.
- If fixing a P2 would materially broaden scope or require a product decision, stop and ask.

### 7. Verify Claims, Not Just Builds

After each fix pass:

- Run repo-required verification where practical.
- Run targeted tests that exercise each fixed bug path directly.
- Add or update regression tests before claiming a finding is fixed.
- Verify route-equivalent paths and nested-state variants from the route/state matrix, not only the originally reported path.
- For UI changes, run browser/widget tests when the behavior is browser-visible.
- For persistence changes, test both in-memory and durable-store paths when both exist.
- If a command cannot run, state exactly why and what risk remains.

### 8. Commit, Push, And Repeat

- Commit only after verification passes, unless the user explicitly accepts broken verification.
- Push the branch so the live PR reflects fixes.
- Re-check live PR comments and CI status after push.
- Run a fresh adversarial review pass against the new head.
- Continue until no active P0/P1/P2 remain, or until blocked by a product decision or user-owned changes.

## Output Rules

During the loop, give concise progress updates. In the final response include:

- PR/branch reviewed.
- Active findings fixed, grouped by severity.
- Tests run and CI state.
- Remaining findings, if any, from the latest pass only.
- Why the loop stopped.

For code-review style output, lead with findings. If there are no findings, say that clearly and mention residual test or scope risk.
