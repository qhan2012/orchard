---
name: herdr-agent-list
description: herdr `agent list` / `agent get` JSON shape and the done/seen rule the fleet board relies on
type: reference
---
Source: github.com/ogulcancelik/herdr @ ee5bfb5, `src/api/schema/agents.rs`, `src/api/schema/response.rs`, `docs/next/.../cli-reference.mdx`.

- `agent list` prints `{"id", "result": {"type": "agent_list", "agents": [AgentInfo]}}`. `agent get` prints `{"result": {"type": "agent_info", "agent": AgentInfo}}`.
- AgentInfo fields orchard uses: `name` (optional), `agent` (kind, e.g. `claude`, `codex`), `agent_status` (`idle|working|blocked|done|unknown`), `pane_id`, `cwd`, `state_change_seq`.
- `done` means idle and not yet seen. Only `agent focus` / `pane focus` mark it seen. `read` does not. So watching never clears the person's "done" signal, and `state_change_seq` stays the same until the state changes.
- herdr has `notification show <title> [--body] [--sound done|request]`, but it shows inside a herdr client. orchard uses its own local `fleet.notify` command instead, because the person may not have a herdr client open on that target.
