# 2026-11-15 worklog

## 1. Proposal: crosscheck gates
- Need (from user): while a worker understands the plan, breaks it down, designs experiments, and runs them, the master must crosscheck. Today `/check` reads status only.
- DECISION (user): the master does the crosscheck. The person reviews only the exceptions.
- Ground truth read first: `DESIGN.md`, `CLAUDE.md`, `/publish`, `/check`, `tasks/TEMPLATE.md`, and the pinned harness `CLAUDE.md` (fc24f24).
- Result: `docs/proposals/crosscheck.md`. Three gates (`plan`, `design`, `result`) as files in the workspace `reports/gates/`, a new skill `/review` that runs in a subagent, and three more lines in `/check`. No code.
- Fit with earlier decisions: the flow does not stop for the person (a gate waits for the master; the person decides a design only above a cost limit); the master's context stays small (review in a subagent); cross-model review stays out of scope.
- Status: proposal. Not agreed, not built. It has 8 open questions for the person; the cost limit `ask_above` (default 8 resource-hours) is a guess.
- Branch note: this branch held the v0.1 session registry (PR #2), written before the rewrite. `main` now covers that need with `started_by` in the task file and `/adopt`. The branch was merged with `main` and takes its tree; the registry code is not in the tree.

## 2. Proposal: two levels of check; metrics in the light check (2026-11-16)
- DECISION (user): two levels. The light check (`/check`) runs on a cadence, for example every 30 minutes. The deep check (`/review`) is the crosscheck.
- DECISION (user): the light check also extracts metrics; they are part of each report.
- Design: the worker appends metrics to `reports/metrics.log`, one line per reading. A passed design verdict holds a `## Watch` list. The light check reads the metrics tail, reports the newest values, compares them with the watch list, and writes `metrics:` to the task file. The deep check runs only on an event (a gate waits, a `watch:` line, or the person asks), never on a clock.
- Proposal sections changed: 2a (new), 4 (design items 4 and 10, metrics.log), 5 (verdict `## Watch`), 6 and 6a, 9, 10, 11 (questions 9 and 10).
