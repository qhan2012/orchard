# 2026-11-15 worklog

## 1. Proposal: crosscheck gates
- Need (from user): while a worker understands the plan, breaks it down, designs experiments, and runs them, the master must crosscheck. Today `/check` reads status only.
- DECISION (user): the master does the crosscheck. The person reviews only the exceptions.
- Ground truth read first: `DESIGN.md`, `CLAUDE.md`, `/publish`, `/check`, `tasks/TEMPLATE.md`, and the pinned harness `CLAUDE.md` (fc24f24).
- Result: `docs/proposals/crosscheck.md`. Three gates (`plan`, `design`, `result`) as files in the workspace `reports/gates/`, a new skill `/review` that runs in a subagent, and three more lines in `/check`. No code.
- Fit with earlier decisions: the flow does not stop for the person (a gate waits for the master; the person decides a design only above a cost limit); the master's context stays small (review in a subagent); cross-model review stays out of scope.
- Status: proposal. Not agreed, not built. It has 8 open questions for the person; the cost limit `ask_above` (default 8 resource-hours) is a guess.
- Branch note: this branch held the v0.1 session registry (PR #2), written before the rewrite. `main` now covers that need with `started_by` in the task file and `/adopt`. The branch was merged with `main` and takes its tree; the registry code is not in the tree.
