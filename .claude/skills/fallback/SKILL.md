---
name: fallback
description: "Move a task to the local runner after the remote kills its agent: make a local harness, bring the state back, add the Remote block, and start a local agent. Use when kills reaches 2 or the person asks to run a task locally."
argument-hint: "<task>"
---

# Move a task to the local runner

Do this when `kills` reaches 2, or when the person says so. It needs the person for the directory review, so at night it waits for them. For a task with `started_by: person`, do it only when the person says so. The new local agent runs in session `orchard`: set `session: orchard`, `agent_name: <task>`, and `started_by: orchard` in the task file.

`E` is the target's `enter` command. Remote form: put the whole remote command in single quotes, `E '<command>'` (`CLAUDE.md`, Remote-control rules).

1. **Make the local harness.** Do the directory part of `/publish` step 3 (show the local directory and its disk use; wait for the person) and then step 4, both locally, with the `harness:` sha from the task file (not `HARNESS`, which can be newer). The local directory is `~/myworks/<task>` unless the person chooses another. If it exists, stop and tell the person.
2. **Bring the state back.** Copy from the remote workspace to the local one: `README.md`, `MEMORY.md`, `memory/`, `reports/`. Example: `E 'cd <remote workspace> && tar -cf - $(ls -d README.md MEMORY.md memory reports 2>/dev/null)' | tar -C <local workspace> -xf -`. This copies only the items that exist (a workspace can have no `MEMORY.md`). Leave `codebases/` and `experiments/` on the remote.
3. **Add the `### Remote` block** to the local `README.md`. The block text is in `.claude/skills/publish/blocks.md`. `Remote dir` is the old remote workspace.
4. **Old agent.** If the remote agent still runs (the person asked for the move), ask the person before you close it (`/close` step 5). Do not leave two agents on one task without telling the person.
5. **Start a local agent** (`/publish` step 7, no `E`) with the prompt plus: "Read the worklog first and continue from the last entry."
6. **Record.**
   - Task file: `runner: local`, `workspace: local:<local workspace>`, `remote_dir`, `status: running`.
   - `targets.yaml`: set the machine's `runner` to `local`.
   - `memory/target-<target>.md`: add "kills agents" with what you saw, and `(verified date, task <task>, kills=N)`.
