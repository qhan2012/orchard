# Check a task

The person decides when and how often to check, at runtime. If they give a cadence, write it to `check:` in the task file and follow it. With no cadence, check only when asked.

For each task to check (default: every task with `status: running`):

1. **Agent state.** `herdr --session orchard agent list` on the side where the agent runs. Find the agent named `<task>`.
2. **Harness files.** In the workspace: `ls reports/` and `tail -n 30 reports/*_worklog.md`.
3. **Decide the status** (DESIGN.md 5):
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
   - `killed`: add 1 to `kills`. If `kills` is 2 or more, do `runbooks/fallback.md`. Otherwise start the agent again (publish step 6) with the prompt plus: "Read the worklog first and continue from the last entry."
5. **Write back.** Update `status`, `last_checked`, `kills`, and `latest` in the task file.

A herdr timeout is not proof of failure. Read the screen before you send a prompt again.
