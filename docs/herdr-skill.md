# orchard and the herdr 0.8.2 skill

herdr ships an agent skill. It teaches a coding agent how to control the herdr session that the agent runs in. This file compares that skill with what orchard's own skills do with herdr, and says which one the master follows.

Source: `skills/herdr/SKILL.md` and `src/` of herdr at tag `v0.8.2` (github.com/herdrdev/herdr). Read from the source on 2026-11-14. Not run against a live herdr.

## What the skill is

- One Markdown file. herdr 0.8.2 compiles it into the binary (`src/main.rs`, `include_str!`), and `herdr --skill` prints it. So each machine can print the skill that matches its own herdr version.
- Its scope is **the session of the pane that the agent runs in**. Its first rule: if `HERDR_ENV` is not `1`, say so and stop.
- It covers: the layout (workspace, tab, pane), agent commands (`start`, `prompt`, `wait`, `read`, `get`, `send-keys`), pane commands (`split`, `run`, `wait-output`, `read`), and safety rules.
- It has no machines, no SSH, no task files, no memory, and no rule for who owns an agent. Those are orchard's.

## Where orchard is inside the skill's scope, and where it is not

| Where the master runs `herdr` | `HERDR_ENV` | Skill applies? |
|---|---|---|
| In its own pane, for a local worker (`runner: local`, `research`) | `1` | Yes |
| On a target: `E 'herdr --session orchard ...'` | not set (an SSH shell) | No. The skill says to stop there |
| Locally, when the master is not inside herdr (`--session orchard`) | not set | No |

So for a remote worker, the skill gives no permission and no procedure. orchard's skills are the only procedure there. The command syntax is still the same, because it is the same CLI.

## Line by line

| Topic | herdr 0.8.2 skill | orchard | Result |
|---|---|---|---|
| Gate | Stop if `HERDR_ENV` is not `1` | Controls a remote server from an SSH shell with `--session orchard` | **orchard wins.** The person's design: the master is local, the worker is remote |
| Where a new agent goes | A sibling pane in the current tab. No new workspace unless the person asks | One herdr workspace for each worker (`workspace create --cwd W --no-focus --label <task>`) | **orchard wins.** The person asked for this layout through the design: `/close` closes one herdr workspace and removes only that worker |
| Working directory | Keep the caller's (`--cwd "$PWD"`) | The task workspace `W` | **orchard wins** |
| Session | The pane's own session. No `--session` | `--session S` on every command, `S` from the task file | **Same result** when `S` is the pane's session. See "Session selection" |
| Syntax authority | The installed binary: `herdr --help`, then `herdr agent`, `herdr pane`, ... | `/publish` step 2 said: check against the `cli-reference` of that version | **Take the skill's rule.** It needs no network and it cannot be the wrong version |
| IDs | Read them from the JSON reply. Do not predict them | Reads `.result.root_pane.pane_id`, `workspace_id` | Same |
| Start | `agent start <name> --kind K --pane ID [-- args]`. Blocked at startup: `agent_not_ready`, the name stays | Same command. The text said only "`agent_status` is `blocked`" | **Add the error code** to `/publish` step 7 |
| Prompt | `agent prompt <name> "..." --wait --timeout MS` for normal work | `agent prompt ... --wait --until working --timeout 15000` | **Neither as written.** The skill's `--wait` waits for the turn to end; a worker turn takes hours, and over SSH that holds the connection. No `--wait` gives no proof of delivery. `--until working` returns in seconds and keeps the `agent_prompt_stalled` check (`src/api/wait.rs` `prompt_agent`) |
| Blocked agent | Read the UI, **ask the user** before you answer it | Read the screen, report. Never send keys | Same intent. orchard is stricter |
| Input to an agent's terminal | `agent send-keys` allowed (`esc`, `ctrl+c`); `pane run` and `pane send-text` for raw panes | The guard hook denies `send-keys`, `pane run`, and `pane send-text`. `agent prompt` is the only input | **orchard wins.** Cost: the master cannot interrupt a worker; it can only close it |
| `idle` and `done` | `done` = idle that nobody has seen in a focused UI. A CLI read does not mark it seen | `/check`: "there but stopped" | Same. On a target with no UI attached, the worker in the server's active tab (the first workspace made) finishes as `idle`, and every other worker finishes as `done`. Treat both as "ready" |
| Read output | `--source recent-unwrapped --lines N`. If more lines show no more text, the agent uses the alternate screen: ask it to write the reply to a file | `/check` and `/adopt` read with `recent-unwrapped` | Same read. `/check` must not prompt, so it uses the worklog instead of the file fallback. This is why the harness worklog is the first signal |
| Close | Do not close what you did not create | Rule 2 and `/close` step 5 | Same |
| Server | Never `herdr server stop` from an active session | Guard hook asks the person | Same |
| Bare `herdr` | Do not run it: it opens the TUI | Same | Same |

## Session selection (checked in `src/session.rs`)

herdr chooses the server socket in this order:

1. `--session <name>` on the command line.
2. `HERDR_SOCKET_PATH`. herdr sets it in every pane (`src/integration/env.rs`, `apply_pane_base_env`).
3. `HERDR_SESSION`.
4. The default session.

Two results:

- Inside a pane, a plain `herdr ...` reaches the pane's own session because of `HERDR_SOCKET_PATH`, not because of `HERDR_SESSION`. This is what the skill relies on.
- An explicit `--session` wins over the pane. So inside herdr, a wrong `S` sends the command to another server without an error. `/publish` step 7 therefore takes `S` from `$HERDR_SESSION`, and uses `default` only if that is empty.

## Decision

1. **Do not copy the herdr skill into this repo.** It would be a second procedure for the same commands, it would be wrong for every target with another herdr version, and its gate and layout rules contradict the design.
2. **orchard's skills stay the procedure.** For remote control they are the only one.
3. **Use the skill as the reference for syntax and states.** Print it where the agent runs: `herdr --skill` locally, `E 'herdr --skill'` on a target. It always matches that machine's herdr.
4. **If a herdr skill is installed in the master's Claude Code** (for example with `npx skills add ... -g`), it can load when the person says "herdr". Then the rules below still win.

## Rules for the master

If a herdr skill is loaded in your session, these orchard rules win:

- You control a target's herdr from an SSH shell, where `HERDR_ENV` is not set. The herdr skill says to stop there. Do not stop: this is the design.
- A worker gets its own herdr workspace in directory `W`, not a sibling pane in your tab.
- Send the task prompt with `--wait --until working --timeout 15000`, never with `--wait` alone.
- `agent prompt` is your only input to an agent. Never use `send-keys`, `pane run`, or `pane send-text`, also where the herdr skill shows them.
- Touch only agents that have a task file here.

When a command fails with a usage error (exit 2), or the herdr version is not 0.8.2, do not guess. Ask the binary on that machine: `herdr --help`, then the group with no subcommand (`herdr agent`, `herdr pane`, `herdr workspace`). Never do this with a subcommand that changes state (`herdr workspace create` runs with defaults), and never with bare `herdr`.

## Not decided here (for the person)

- **Workers and the herdr skill.** A worker runs in a herdr pane (`HERDR_ENV=1`). If a herdr skill is installed for that user on that machine, the worker can split panes and start helper agents next to itself. By the skill's default these are sibling panes in the worker's own herdr workspace, so `/close` step 5 removes them too. `/check` does not see them as tasks. No rule here allows or forbids this.
- **`agent wait`.** `herdr agent wait <task> --timeout MS` could replace a short `/loop` for a local worker. Not used: a check must also read the worklog.
