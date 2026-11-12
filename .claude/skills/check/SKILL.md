---
name: check
description: "Check one task or all running tasks: read herdr agent state and the workspace worklog and summary, decide the status, act, and write it back to the task file. Use when the person asks for status, or as the prompt of /loop."
argument-hint: "[<task>]"
---

# Check a task

Argument: a task name. With no argument, check every open task: `status` is `running`, `blocked`, `idle`, or `killed`.

**When and how often** is the person's decision, at runtime:
- "Check now": do one check.
- "Check `<task>` every 10 minutes": write `check: every 10m` to the task file, then start `/loop 10m /check <task>`. Stop the loop when the task is `done`, `blocked`, or `killed`, or after 3 checks in a row that find the target unreachable, and tell the person.
- `/loop` lives only in this session. After a restart, look for tasks with a `check:` value and tell the person which loops to start again.

For each task to check, `S` is the task's `session`, `A` is its `agent_name` (default: the task name), and `E` is the target's `enter` command (none for a local agent). Remote form: put the whole remote command in single quotes, `E '<command>'` (`CLAUDE.md`, Remote-control rules).

1. **Agent state.** `herdr --session S agent list` on the side where the agent runs. Find the agent `A`. Skip the agent named `master`: that is you.
   If the command fails, find out why before you decide anything:
   - `E true` fails (ssh exit 255, timeout): the target is **unreachable**. You know nothing about the agent. Keep the task's `status`, write `latest: unreachable since <time>`, report, and stop here for this task. Do not add to `kills`. Do not restart.
   - `E true` works, and `herdr --session S status server` says no server: the server is gone, so the agent is gone.
   - The server answers and `A` is not in the list: the agent is gone. Run `agent list` a second time to confirm.
2. **Harness files.** In the workspace directory: `ls reports/` and `tail -n 30 reports/*_worklog.md`. An adopted task can have no harness files. Then use the agent state and its screen only: `idle` or `done` means "finished a turn". Read the screen and report it; only the person says the task is done.
3. **Decide the status** (`DESIGN.md` 5):
   - a `reports/*_summary.md` exists and the agent is not `working`: `done`
   - a summary exists and the agent is `working`: `running` (the person gave it more work after `done`). When it stops again, it is `done` again.
   - herdr says `blocked`, or the worklog has a new `BLOCKER:`: `blocked`
   - the agent is gone (confirmed in step 1; the target is reachable) and no summary: `killed`
   - agent stopped, no summary: `idle`
   - otherwise: `running`
4. **Act.**
   - `running`: do nothing.
   - `done`: read the summary and report it to the person. Stop any `/loop` for this task. Leave the agent running, so the person can ask it more. Cleanup happens only when the person closes the task (`/close <task>`).
   - `blocked`: `herdr --session S agent read A --source recent-unwrapped --lines 120`. Report to the person. Never send keys to approve.
   - `idle`: read the screen. If it waits for input that the plan already answers, answer it. Otherwise report. For `started_by: person`, report only.
   - `killed`, `started_by: person`: report it. Do not restart it and do not run `/fallback` unless the person says so.
   - `killed`, `started_by: orchard`: add 1 to `kills`. Before a restart, make sure no agent `A` runs (step 1), so there are never two. If `kills` is 2 or more, run `/fallback <task>`. Otherwise start the agent again (`/publish` step 7) with the prompt plus: "Read the worklog first and continue from the last entry."
5. **Write back.** Update `status`, `last_checked`, `kills`, and `latest` in the task file.

A herdr timeout is not proof of failure. Read the screen before you send a prompt again.
