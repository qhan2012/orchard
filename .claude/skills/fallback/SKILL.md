---
name: fallback
description: "Move a task to the local runner after the remote kills its agent: make a local harness, bring the state back, add the Remote block, and start a local agent. Use when kills reaches 2 or the person asks to run a task locally."
argument-hint: "<task>"
---

# Move a task to the local runner

Do this when `kills` reaches 2, or when the person says so. For a task with `started_by: person`, do it only when the person says so. The new local agent runs in session `orchard`: set `session: orchard`, `agent_name: <task>`, and `started_by: orchard` in the task file.

1. **Make the local harness.** Do `/publish` step 3 locally, with the `harness:` sha from the task file (not `HARNESS`, which can be newer). If `~/myworks/<task>` exists locally, stop and tell the person.
2. **Bring the state back.** Copy from the remote workspace to the local one: `README.md`, `MEMORY.md`, `memory/`, `reports/`. Example: `E 'tar -C ~/myworks/<task> -cf - README.md MEMORY.md memory reports' | tar -C ~/myworks/<task> -xf -`. Leave `codebases/` and `experiments/` on the remote.
3. **Add the `### Remote` block** to the local `README.md` (`DESIGN.md` 4). `Remote dir` is the old remote workspace.
4. **Start a local agent** (`/publish` step 6, no `E`) with the prompt plus: "Read the worklog first and continue from the last entry."
5. **Record.**
   - Task file: `runner: local`, `workspace: local:~/myworks/<task>`, `remote_dir`, `status: running`.
   - `targets.yaml`: set the machine's `runner` to `local`.
   - `memory/target-<target>.md`: add "kills agents" with what you saw, and `(verified date, task <task>, kills=N)`.
