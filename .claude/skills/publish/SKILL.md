---
name: publish
description: "Publish a task: choose and review the workspace directory, make the workspace from qhan2012/harness under myworks/<task>, write the plan into its README, seed memory, and start the worker agent in herdr. Use when the person asks to plan, start, or publish a task on a target."
argument-hint: "<task>"
---

# Publish a task

`E` is the target's `enter` command. Remote form: put the whole remote command in single quotes, `E '<command>'` (`CLAUDE.md`, Remote-control rules). With `runner: herdr`, the workspace is on the target: put `E` in front of each workspace command. With `runner: local`, the workspace is local: run the commands as they are.

`W` is the workspace directory: `<workdir>/<task>`. `<workdir>` is the target's `workdir` in `targets.yaml`. The default is `~/myworks`. The last part of `<workdir>` is always `myworks`.

**One review, not three.** Steps 0 to 2 collect facts and make nothing. Step 3 shows the person one review screen (launch card, plan, directory and disk) and waits once. Ask earlier only if you cannot go on: the kind is not clear, or a check in step 2 fails.

0. **Decide the kind.** Every task gets its own workspace made from the harness. The kind decides where it is and what the worker may do.

   | The person wants | `kind` | Agent and workspace | Remote access |
   |---|---|---|---|
   | To run, build, or debug something on one target | `experiment` | on the target (`runner: herdr`), or local if the target kills agents (`runner: local`) | read and write on that target |
   | To study results from one or more targets, with web search; a deep dive, a comparison, a report | `research` | local (`target: local`, `runner: local`) | read-only, on every target in `remotes` |

   If the request does not say which, ask. Do not guess.
   **Task name.** It is also the herdr agent name, so it must match `[a-z][a-z0-9_-]{0,31}`: a lowercase letter first, then lowercase letters, digits, `_`, or `-`, 32 characters at most. It must not be `master`, and no `tasks/<task>.md` may exist. If the person's name does not fit, propose one that does.
   **Agent kind** (herdr `--kind`: `claude`, `codex`, `cursor`, ...). Take the first that applies: (1) what the person said in the request; (2) `agent` of the place where the agent runs, in `targets.yaml` (the target, or the `local` entry for `runner: local` and `research`); (3) `claude`. Write it to `agent:` in the task file.
   Prepare the launch card. It is part of the review screen in step 3:
   ```
   Task:     <task>
   Kind:     experiment | research
   Agent:    <agent kind>, runs on <target | local>
   Workspace: <where>:<workdir>/<task>
   Remotes:  <for research: each target and the directories to read>
   Args:     <agent_args, for example --dangerously-skip-permissions>
   Goal:     <one line>
   ```
   For `research`: read `tasks/*.md` to find the workspaces of the tasks to study. For a closed task, use the local copy in `reports/tasks/<task>/`. Write the list to `remotes:` in the task file.
1. **Plan.** Copy `tasks/TEMPLATE.md` to `tasks/<task>.md`. Fill the header and the plan. For `kind: experiment`, add these two lines to the plan Constraints:
   - "Give every scheduler job a name that starts with `<task>-`."
   - "Cancel your jobs before you write the summary."
   If the target has a `datadir`, add: "Put large outputs (checkpoints, datasets, full logs) under `<datadir>/<task>/`."
   The person reviews the plan in step 3.
2. **Check the target.** `ssh -o BatchMode=yes <host> true` must pass (for `research`: every target in `remotes`). If it fails, tell the person. Do not try to bypass it.
   A remote agent needs network access to its model API. If `memory/target-<target>.md` says the target has none, use `runner: local`.
   **Check the agent CLI** where the agent will run: `command -v <cli>` (`claude` → `claude`, `codex` → `codex`, `cursor` → `cursor-agent`). Login cannot be checked the same way for every CLI: if `memory/target-<name>.md` does not say that this kind is logged in there, ask the person, then record the answer. If the CLI is missing or not logged in, stop and tell the person. Do not change to another kind yourself.
   **Check the account** where the agent will run: `id -u`. If it is `0` (root) and the `agent_args` have `--dangerously-skip-permissions`, stop and tell the person: Claude Code is expected to refuse that flag as root. Do not start the agent to find out.
   Run `herdr --version` where the agent will run. The skills are checked against herdr 0.8.2 (memory `herdr-cli-facts`). If the version is different, check each herdr command below against that version's `cli-reference` first, and record the version in `memory/target-<target>.md`.
3. **Review with the person: one screen, one answer** (`DESIGN.md` 4a). Do this for every new workspace. First collect the disk facts, on the side where the workspace will be (and for the remote work directory with `runner: local`).
   ```bash
   df -h ~ <workdir> 2>&1            # home and the workdir filesystem
   quota -s 2>/dev/null              # can be empty; shared filesystems need a site command
   du -sh <workdir> 2>/dev/null      # what myworks already uses
   df -h -x tmpfs -x devtmpfs        # other mounted disks = alternative locations
   ```
   Then show the person one review screen, in this order:
   - the launch card from step 0
   - the plan from step 1 (the five items)
   - the directory you will make: `W`
   - disk use: size, used, free, and quota if known, for home and for `<workdir>`
   - alternatives: other writable disks, each as `<disk>/$USER/myworks`, with free space and what memory `target-<target>` says about them (purged? backed up? seen on compute nodes?)
   - your recommendation, in this order: (1) a disk that is not purged and that compute nodes can see; (2) home, if the quota is enough; (3) if only a purged disk has space: workspace in home, and that disk as `datadir`.

   Wait for the person's answer. One "yes" accepts the card, the plan, and the directory. If they change one part, show only that part again. Do not make the directory before they agree.
   Home must keep free space in every case: the agent and herdr write their state under home.
   **First use of a target** (no `workdir` in `targets.yaml`): also ask what commands cannot show: the quota command for shared filesystems, the file-count quota, the purge policy, and if compute nodes see the same path. Write the choice to `targets.yaml` (`workdir`, optional `datadir`) and the reasons to `memory/target-<target>.md`. For a new disk: `mkdir -p <workdir> && chmod 700 <workdir>`.
4. **Make the workspace** (`DESIGN.md` 4b). Read `<url> <sha>` from the one non-comment line of `HARNESS` in this repo.
   ```bash
   test -e W && echo EXISTS     # EXISTS: stop and tell the person
   git init -q W
   git -C W fetch -q --depth 1 <url> <sha>
   git -C W checkout -q FETCH_HEAD
   git -C W rev-parse HEAD      # must equal <sha>; write it to `harness:` in the task file
   rm -rf W/.git                # so nothing is pushed to qhan2012/harness
   ```
   If the target cannot reach GitHub (`git fetch` fails or times out): make the same copy in a local temporary directory with the commands above, then send it: `tar -C <tmp> -cf - . | E 'mkdir W && tar -C W -xf -'`. Record "no GitHub access" in `memory/target-<target>.md`, and use this way first next time.
   Fetch by commit needs the full 40-character sha. Do not use the latest main: a new harness version comes only through a change to `HARNESS`.
   With `runner: local` and `kind: experiment`, also make the remote work directory: `E 'test -e <remote W> && echo EXISTS || mkdir -p <remote W>'`. A `research` task makes nothing on a remote.
   Write the absolute path of `W` to `workspace:` (and `remote_dir:`) in the task file.
5. **Write the plan.** Replace the `_TODO_` line under `## Project Scope` in the workspace `README.md` with the five plan items. With `runner: local` and `kind: experiment`, add the `### Remote` block (`DESIGN.md` 4). For `kind: research`, add the `### Remotes (read-only)` block (`DESIGN.md` 4e).
   To write a remote file: `E 'cat > W/README.md' < local-copy`.
6. **Seed memory.** If `memory/target-<target>.md` exists here (for `research`: one per target in `remotes`), copy it to the workspace `memory/` and add its line to the workspace `MEMORY.md`. The harness copy has no `MEMORY.md`: make it first, with the heading `# Memory index`.
7. **Start the agent in herdr** (see memory `herdr-cli-facts`). Use session `orchard`. Set `session: orchard` and `agent_name: <task>` in the task file.
   ```bash
   herdr --session orchard status server      # if no server: setsid nohup herdr --session orchard server > ~/.orchard-herdr.log 2>&1 < /dev/null &
   herdr --session orchard workspace create --cwd W --no-focus --label <task>   # read .result.root_pane.pane_id
   herdr --session orchard agent start <task> --kind <agent> --pane <pane_id> [-- <agent_args for this kind>]
   herdr --session orchard agent get <task>     # read agent_status before you send the prompt
   herdr --session orchard agent prompt <task> "Read README.md § Project Scope and CLAUDE.md. Then do the task in autonomous long-run mode."
   ```
   On a target, each line is one remote command in single quotes, for example:
   `E 'herdr --session orchard agent prompt <task> "Read README.md § Project Scope and CLAUDE.md. Then do the task in autonomous long-run mode."'`
   **First-start dialog.** A new directory often makes the agent ask a question before it accepts input (trust this folder, log in, choose a mode). Then `agent_status` is `blocked`, and herdr refuses the prompt (`agent_blocked`). Do not send keys. Read the screen (`agent read <task> --lines 40`), tell the person what it asks, and ask them to answer it in the herdr TUI (`herdr --session orchard`, or `herdr --remote <host> --session orchard` for a target). When the status is `idle`, send the prompt. Record in `memory/target-<target>.md` what this agent kind asks at first start there.
   After the prompt, run `agent get <task>` once more: the status must be `working`. If it is not, read the screen before you do anything else.
   Never run bare `herdr`: it opens the TUI.
   **Permissions.** Workers run without permission prompts (the person's decision, `DESIGN.md` 4f), both `experiment` and `research`. For `claude`, the default `agent_args` are `--dangerously-skip-permissions`. An `agent_args` entry for the kind in `targets.yaml` replaces the default. For another kind with no `agent_args`, start without them and tell the person that the agent can stop at approval prompts; do not guess a flag. Show the arguments on the launch card (`Args:` line).
   For `runner: local`, the master usually runs inside the local `orchard` session, so the server is already running: skip the start. The worker gets its own herdr workspace (`--no-focus`), so the master pane does not change.
8. **Record.** Set `status: running` in the task file. Add a worklog entry with the task, target, runner, workspace, and harness commit.
   After the worker's first job runs, check that the compute node sees `W` (and `datadir`). Record the result in `memory/target-<target>.md`.
