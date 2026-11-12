---
name: check
description: "Check one task or all open tasks: read herdr agent state and the workspace worklog and summary, decide each status, write it to the task file, and return a short report. Runs in a subagent so its command output stays out of the master's context. Use when the person asks for status, or as the prompt of /loop."
argument-hint: "[<task>]"
context: fork
---

# Check a task

You run as a subagent of the master. You **look, decide, record, and report**. You do not act: do not start, prompt, restart, stop, or move any agent, and do not talk to the person. The master acts on your report (`CLAUDE.md`, "After a check").

Argument: a task name. With no argument, check every open task: `status` is `running`, `blocked`, `idle`, or `killed`.

For each task, read `tasks/<task>.md`. `S` is its `session`, `A` is its `agent_name` (default: the task name), `W` is its workspace path, and `E` is the target's `enter` command from `targets.yaml` (none for a local agent). Remote form: put the whole remote command in single quotes, `E '<command>'`. Use `ssh -o BatchMode=yes`.

1. **Agent state.** `herdr --session S agent list` on the side where the agent runs. Find the agent `A`. Ignore the agent named `master`.
   If the command fails, find out why before you decide anything:
   - `E true` fails (ssh exit 255, timeout): the target is **unreachable**. You know nothing about the agent. Keep the task's `status`, add 1 to `unreachable` in the task file, and go to step 4.
   - `E true` works, and `herdr --session S status server` says no server: the server is gone, so the agent is gone.
   - The server answers and `A` is not in the list: the agent is gone. Run `agent list` a second time to confirm.
   When the target is reachable, set `unreachable: 0`.
2. **Harness files.** In the workspace directory: `ls W/reports/` and `tail -n 30 W/reports/*_worklog.md`. An adopted task can have no harness files. Then use the agent state and its screen only: `idle` or `done` in herdr means "finished a turn", and you report it as `idle`; only the person says that such a task is done.
3. **Decide the status** (`DESIGN.md` 5). Take the first that fits:
   - a `reports/*_summary.md` exists and the agent is not `working`: `done`
   - a summary exists and the agent is `working`: `running` (the person gave it more work after `done`)
   - herdr says `blocked`, or the worklog has a new `BLOCKER:`: `blocked`
   - the agent is gone (confirmed in step 1; the target is reachable) and no summary: `killed`
   - the agent is there but stopped, no summary: `idle`
   - otherwise: `running`

   For `blocked` and `idle`, read the screen: `herdr --session S agent read A --source recent-unwrapped --lines 60`. For `done`, read the top section of the summary.
4. **Record.** In the task file, update `status`, `last_checked` (run `date` for it), `latest` (one line), and `unreachable`. Do not change `kills`, `check`, or any other field.
5. **Report.** Return only this, at most 8 lines for each task. Do not paste command output.
   ```
   <task> | <status> | was <old status> | <target>
   latest: <one line of progress, from the worklog>
   <for done: the result and the blockers or decisions from the summary, 1 to 4 lines>
   <for blocked or idle: what the agent asks or waits for, 1 to 3 lines>
   <for killed: what you saw (no agent, or no server), and started_by>
   <for unreachable: the ssh error, and the unreachable count>
   ```

A herdr timeout is not proof of failure. If a command times out, run it once more before you decide.
