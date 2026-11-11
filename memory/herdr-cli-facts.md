---
name: herdr-cli-facts
description: herdr v0.9.5 CLI behaviour that orchard relies on
type: reference
---
Source: github.com/ogulcancelik/herdr @ ee5bfb5 (2026-10-29), `skills/herdr/SKILL.md`, `docs/next/website/src/content/docs/cli-reference.mdx`.

- `--session <name>` is a global prefix and selects an independent server.
- `herdr server` runs the headless server in the foreground. The server ignores SIGHUP. Stop it with `herdr server stop` or SIGTERM.
- Control commands print JSON on stdout. On a timeout or server error, they print JSON on stderr and exit 1. Usage errors exit 2.
- `workspace create --cwd P --no-focus` returns `.result.root_pane.pane_id`. `agent start NAME --kind K --pane ID` needs a pane where the shell is at its prompt.
- Agent states: `idle` and `done` mean ready. `blocked` means an approval or question UI is open. `unknown` does not prove that the work completed.
- A timeout does not prove that a prompt was not delivered. Read the agent's output before you retry.
- `herdr --machine` uses only saved profiles. orchard does not use it. It runs `herdr` on the target over SSH or srun.
- Do not run bare `herdr`, because it launches the TUI.
