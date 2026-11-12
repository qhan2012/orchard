---
name: herdr-cli-facts
description: herdr v0.9.5 CLI behaviour that the skills rely on
type: reference
---
- `--session <name>` is a global prefix and selects an independent server. (verified 2026-11-09, herdr source @ ee5bfb5 `docs/next/.../cli-reference.mdx`)
- `herdr server` runs the headless server in the foreground. It ignores SIGHUP. Stop it with `herdr server stop` or SIGTERM. (verified 2026-11-09, same source)
- Control commands print JSON on stdout. On a timeout or server error they print JSON on stderr and exit 1. Usage errors exit 2. (verified 2026-11-09, same source)
- `workspace create --cwd P --no-focus` returns `.result.root_pane.pane_id`. `agent start NAME --kind K --pane ID` needs a pane where the shell is at its prompt. (verified 2026-11-09, `skills/herdr/SKILL.md` @ ee5bfb5)
- `agent list` returns `.result.agents[]` with `name`, `agent` (kind), `agent_status`, `pane_id`, `cwd`. (verified 2026-11-11, `src/api/schema/agents.rs` @ ee5bfb5)
- Agent states: `idle` and `done` mean ready. `blocked` means an approval or question UI is open. `unknown` does not prove that the work completed. (verified 2026-11-09, SKILL.md)
- A timeout does not prove that a prompt was not delivered. Read the agent's output before you retry. (verified 2026-11-09, SKILL.md)
- Do not run bare `herdr`: it launches the TUI. (verified 2026-11-09, SKILL.md)
- None of this is verified against a running herdr yet. (2026-11-11)
