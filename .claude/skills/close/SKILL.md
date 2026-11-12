---
name: close
description: "Close a done task when the person says so: record the agent session id, check for leftover scheduler jobs, copy reports and memory back, collect lessons, and close the worker's herdr workspace. Use when the person says to close, finish, or clean up a task."
argument-hint: "<task>"
---

# Close a task

Only the person closes a task. `done` alone is not a reason to close. If the target is unreachable, stop and tell the person: do not close a task that you cannot see.

For a task with `started_by: person`: do steps 2 to 4 only, then set `status: closed`. Do not touch the agent.

`E` is the target's `enter` command (none for a local agent). Remote form: put the whole remote command in single quotes, `E '<command>'` (`CLAUDE.md`, Remote-control rules). `S` is the task's `session`, `A` its `agent_name`, `W` its workspace path.

1. **Record the session id.** `E herdr --session S agent get A`. If the reply has `agent_session`, write its id to `agent_session:` in the task file. With it, the conversation can be resumed later (for example `claude --resume <id>` in `W`). If it is absent, tell the person that the agent's conversation ends with the close.
2. **Check leftover jobs.** On a target with a scheduler, list the person's jobs whose name starts with `<task>-` (Slurm: `squeue --me --name` does not match a prefix, so use `squeue --me --format='%i %j %T' | grep ' <task>-'`). If any is left, show it and ask. Do not cancel it yourself. Another scheduler is not covered yet: tell the person to check.
3. **Copy the record back.** `E 'cd W && tar -cf - $(ls -d README.md MEMORY.md memory reports 2>/dev/null)' | tar -C reports/tasks/<task> -xf -` (make `reports/tasks/<task>/` first; this copies only the items that exist). With `runner: local` the files are already local: skip.
4. **Collect memory.** Read the task `MEMORY.md`. Move only lessons that hold across tasks into master memory (mostly `memory/target-<target>.md`), each with `(verified date, task <task>)`.
5. **Close the worker.** `E herdr --session S agent get A` gives its `workspace_id`. Then `E herdr --session S workspace close <workspace_id>`. Check with `agent list` that only this agent is gone. Never close the workspace of `master`.
6. **Record.** Set `status: closed` in the task file. Add a worklog entry. Keep the directory `W` unless the person says to remove it.

Do not stop the herdr server here. Stop a server only when the person asks: first show `E herdr --session S agent list` and `pane list`, then `E herdr --session S server stop`. Never stop the local `orchard` server.
