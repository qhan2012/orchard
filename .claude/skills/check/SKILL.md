---
name: check
description: "Check one task or all running tasks: read herdr agent state and the workspace worklog and summary, decide the status, act, and write it back to the task file. Use when the person asks for status, or as the prompt of /loop."
argument-hint: "[<task>]"
---

# Check a task

Argument: a task name. With no argument, check every task with `status: running`.

**When and how often** is the person's decision, at runtime:
- "Check now": do one check.
- "Check `<task>` every 10 minutes": write `check: every 10m` to the task file, then start `/loop 10m /check <task>`. Stop the loop when the task is `done`, `blocked`, or `killed`, and tell the person.
- `/loop` lives only in this session. After a restart, look for tasks with a `check:` value and tell the person which loops to start again.

For each task to check:

1. **Agent state.** `herdr --session orchard agent list` on the side where the agent runs. Find the agent named `<task>`.
2. **Harness files.** In the workspace: `ls reports/` and `tail -n 30 reports/*_worklog.md`.
3. **Decide the status** (`DESIGN.md` 5):
   - a `reports/*_summary.md` exists: `done`
   - herdr says `blocked`, or the worklog has a new `BLOCKER:`: `blocked`
   - no agent, or herdr unreachable, and no summary: `killed`
   - agent stopped, no summary: `idle`
   - otherwise: `running`
4. **Act.**
   - `running`: do nothing.
   - `done`: read the summary and report it to the person. Then collect memory: read the task `MEMORY.md`, and move only lessons that hold across tasks into master memory, with `(verified date, task <task>)`.
   - `blocked`: `herdr --session orchard agent read <task> --source recent-unwrapped --lines 120`. Report to the person. Never send keys to approve.
   - `idle`: read the screen. If it waits for input that the plan already answers, answer it. Otherwise report.
   - `killed`: add 1 to `kills`. If `kills` is 2 or more, run `/fallback <task>`. Otherwise start the agent again (`/publish` step 6) with the prompt plus: "Read the worklog first and continue from the last entry."
5. **Write back.** Update `status`, `last_checked`, `kills`, and `latest` in the task file.

A herdr timeout is not proof of failure. Read the screen before you send a prompt again.
