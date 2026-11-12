---
name: herdr-cli-facts
description: herdr v0.8.2 CLI behaviour that the skills rely on (the version the person uses)
type: reference
---
The person uses herdr 0.8.2. (stated 2026-11-11)
Source for every line below: github.com/ogulcancelik/herdr tag `v0.8.2`, `docs/versions/0.8.2/.../cli-reference.mdx` and `src/`. Checked against the source, not against a running herdr. (verified 2026-11-11)

- `--session <name>` is removed from the arguments before any command runs (`src/session.rs` `configure_from_args`), so it works as a prefix on control commands such as `herdr --session orchard agent list`. (verified 2026-11-11, v0.8.2 source)
- `herdr server` runs the headless server in the foreground. Stop it with `herdr server stop`. `herdr status server` shows its status. The 0.8.2 docs say nothing about SIGHUP, so start it with `setsid nohup ... &`. (verified 2026-11-11, v0.8.2 docs)
- `workspace create [--cwd PATH] [--label TEXT] [--no-focus]` returns the root pane as `.result.root_pane.pane_id`. (verified 2026-11-11, v0.8.2 docs)
- `agent start <name> --kind KIND --pane ID [--timeout MS]` needs a pane whose shell is at its prompt. The timeout must be more than 3000 and at most 300000 ms (default 30000). Names match `[a-z][a-z0-9_-]{0,31}`. Kinds include `claude`, `codex`, `opencode`. (verified 2026-11-11, v0.8.2 docs)
- `agent prompt <target> <text> [--wait] [--until STATUS] [--timeout MS]`. If the agent is `blocked`, it returns `agent_blocked` and sends nothing. With `--wait`, no activity in 5 s gives `agent_prompt_stalled`. (verified 2026-11-11, v0.8.2 docs)
- `agent list` prints `.result.agents[]` with `name`, `agent` (kind), `agent_status`, `pane_id`, `cwd`, `state_change_seq`. (verified 2026-11-11, v0.8.2 `src/api/schema/agents.rs`)
- `agent_status` is one of `idle`, `working`, `blocked`, `done`, `unknown`. `idle` and `done` mean ready. `blocked` means an approval or question UI is open. `unknown` does not prove the work completed. (verified 2026-11-11, v0.8.2 `src/api/schema/common.rs` and docs)
- `agent rename <target> <name>|--clear` names an already detected agent. A name is cleared when the agent exits. (verified 2026-11-11, v0.8.2 docs)
- `session list [--json]` lists sessions. `--session default` selects the default session explicitly (`src/session.rs` `normalize_name`). (verified 2026-11-11, v0.8.2 source)
- `workspace close <workspace_id>` and `pane close <pane_id>` exist. There is no `agent stop`. `pane list [--workspace ID]` lists panes, with or without an agent. (verified 2026-11-11, v0.8.2 docs)
- `agent get` and `agent list` include `agent_session` only when an official herdr integration reported a native session reference. herdr can resume claude, codex, and cursor (executable `cursor-agent`) from it (`src/agent_resume.rs`). (verified 2026-11-11, v0.8.2 docs and source)
- After a server restart, processes are gone. herdr restores layout and cwd; the agent conversation returns only with native agent session restore. (verified 2026-11-11, v0.8.2 docs `session-state`)
- `agent read <target> [--source visible|recent|recent-unwrapped|detection] [--lines N]`. Without `--lines`, recent sources read 80 rows. (verified 2026-11-11, v0.8.2 docs)
- A timeout or server error prints JSON on stderr and exits 1. Usage errors exit 2. A timeout does not prove that a prompt was not delivered. (verified 2026-11-11, v0.8.2 docs)
- With no `--session`, the CLI uses `$HERDR_SESSION` (`src/session.rs`). So inside a herdr pane, a plain `herdr ...` command should reach the pane's own session. Not confirmed on a live herdr. (verified 2026-11-12, v0.8.2 source)
- Do not run bare `herdr`: it opens the TUI. (verified 2026-11-11, v0.8.2 docs)
- Not in 0.8.2 docs: `herdr machine` (saved SSH profiles). The skills do not use it. (verified 2026-11-11, v0.8.2 docs)
