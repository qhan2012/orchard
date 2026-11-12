---
name: adopt
description: "Take over a long-run agent that the person started by hand: find it in herdr on a target or locally, name it, and write a task file with started_by: person so /check can monitor it. Use when the person asks the master to take over, watch, or manage an agent they started."
argument-hint: "<task> [where: target, session, pane or name]"
---

# Adopt a running agent

The person started the agent. The person's request to adopt it is their consent to name it and to monitor it. It is not consent to prompt, restart, stop, or move it.

`E` is the target's `enter` command. For a local agent, run the commands without `E`.

1. **Find the agent.** Use what the person gave: target, session, pane id, agent name, or directory.
   - Session unknown: `E herdr session list --json`. Most hand-started agents are in session `default`.
   - `E herdr --session <session> agent list`. Match by name, `pane_id`, or `cwd`.
   - No match, or more than one: show the candidates (pane id, kind, cwd, status) and ask. Do not guess.
2. **Read it.** `E herdr --session <session> agent read <pane_id or name> --source recent-unwrapped --lines 120`. Learn what it is doing. Send nothing.
3. **Name it.** If it has no name: `E herdr --session <session> agent rename <pane_id> <task>`. Tell the person. If it already has a name, keep that name. The name is the `agent_name` in the task file. A name is cleared when the agent exits; then use its `pane_id`.
4. **Find its workspace.** Its `cwd` from `agent list`. Look for harness files: `README.md` with `## Project Scope`, and `reports/`.
   - Found: `/check` uses them as for any task.
   - Not found: `/check` uses the herdr state and the screen only. Do not add harness files unless the person asks.
5. **Write the task file.** Copy `tasks/TEMPLATE.md` to `tasks/<task>.md`. Set:
   - `started_by: person`, `session`, `agent_name`, `agent` (kind from `agent list`)
   - `target` (or `local`), `runner` (`herdr` if on a target, `local` if on this machine), `workspace: <target>:<cwd>`
   - `harness`: empty, or what the workspace says if it is a harness copy
   - `status` from step 1-2, `kills: 0`, `last_checked`, `latest`
   - Plan section: the person's goal in their words, plus one line on what the screen shows.
6. **Record.** Add a worklog entry: task, where, session, agent name, pane id, and the commands you ran. Ask the person if they want a check cadence (`/loop <interval> /check <task>`).
