---
name: session-registry
description: who started each herdr session; the rule for `herdr down`
type: project
---
- `state/sessions.json` (gitignored, local to the master) records herdr sessions. `started_by` is `orchard` or `user`.
- The user works in two modes (2026-11-11): the master starts everything, or the user starts herdr and agents by hand and the master only watches and prompts. Hand-started sessions are registered with `session adopt`.
- `herdr down` stops a server only if the registry says orchard started it. Not registered, or `user`, needs `--force` and a person's confirmation.
- The registry is a record, not live state. A node reboot or a job timeout does not update it. Check the target before you trust it.
- Only one side drives an agent at a time. Input from the TUI and from `prompt` can mix.
