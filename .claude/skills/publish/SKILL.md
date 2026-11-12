---
name: publish
description: "Publish a task: choose and review the workspace directory, make the workspace from qhan2012/harness under myworks/<task>, write the plan into its README, seed memory, and start the worker agent in herdr. Use when the person asks to plan, start, or publish a task on a target."
argument-hint: "<task>"
---

# Publish a task

`E` is the target's `enter` command. With `runner: herdr`, the workspace is on the target: put `E` in front of each workspace command. With `runner: local`, the workspace is local: run the commands as they are.

`W` is the workspace directory: `<workdir>/<task>`. `<workdir>` is the target's `workdir` in `targets.yaml`. The default is `~/myworks`. The last part of `<workdir>` is always `myworks`.

1. **Plan.** Copy `tasks/TEMPLATE.md` to `tasks/<task>.md`. Fill the header and the plan. Add these two lines to the plan Constraints:
   - "Give every scheduler job a name that starts with `<task>-`."
   - "Cancel your jobs before you write the summary."
   If the target has a `datadir`, add: "Put large outputs (checkpoints, datasets, full logs) under `<datadir>/<task>/`."
   Publish only after the person accepts the plan.
2. **Check the target.** `ssh -o BatchMode=yes <host> true` must pass. If it fails, tell the person. Do not try to bypass it.
   Run `herdr --version` where the agent will run. The skills are checked against herdr 0.8.2 (memory `herdr-cli-facts`). If the version is different, check each herdr command below against that version's `cli-reference` first, and record the version in `memory/target-<target>.md`.
3. **Review the directory with the person.** Do this for every new workspace, on the side where the workspace will be (and for the remote work directory with `runner: local`).
   ```bash
   df -h ~ <workdir> 2>&1            # home and the workdir filesystem
   quota -s 2>/dev/null              # can be empty; shared filesystems need a site command
   du -sh <workdir> 2>/dev/null      # what myworks already uses
   df -h -x tmpfs -x devtmpfs        # other mounted disks = alternative locations
   ```
   Show the person:
   - the directory you will make: `W`
   - disk use: size, used, free, and quota if known, for home and for `<workdir>`
   - alternatives: other writable disks, each as `<disk>/$USER/myworks`, with free space and what memory `target-<target>` says about them (purged? backed up? seen on compute nodes?)
   - your recommendation, in this order: (1) a disk that is not purged and that compute nodes can see; (2) home, if the quota is enough; (3) if only a purged disk has space: workspace in home, and that disk as `datadir`.

   Wait for the person's answer. Do not make the directory before they agree.
   Home must keep free space in every case: the agent and herdr write their state under home.
   **First use of a target** (no `workdir` in `targets.yaml`): also ask what commands cannot show: the quota command for shared filesystems, the file-count quota, the purge policy, and if compute nodes see the same path. Write the choice to `targets.yaml` (`workdir`, optional `datadir`) and the reasons to `memory/target-<target>.md`. For a new disk: `mkdir -p <workdir> && chmod 700 <workdir>`.
4. **Make the workspace** (`DESIGN.md` 4a). Read `<url> <sha>` from the one non-comment line of `HARNESS` in this repo.
   ```bash
   test -e W && echo EXISTS     # EXISTS: stop and tell the person
   git init -q W
   git -C W fetch -q --depth 1 <url> <sha>
   git -C W checkout -q FETCH_HEAD
   git -C W rev-parse HEAD      # must equal <sha>; write it to `harness:` in the task file
   rm -rf W/.git                # so nothing is pushed to qhan2012/harness
   ```
   Fetch by commit needs the full 40-character sha. Do not use the latest main: a new harness version comes only through a change to `HARNESS`.
   With `runner: local`, also make the remote work directory: `E 'test -e <remote W> && echo EXISTS || mkdir -p <remote W>'`.
   Write the absolute path of `W` to `workspace:` (and `remote_dir:`) in the task file.
5. **Write the plan.** Replace the `_TODO_` line under `## Project Scope` in the workspace `README.md` with the five plan items. With `runner: local`, add the `### Remote` block (`DESIGN.md` 4).
   To write a remote file: `E 'cat > W/README.md' < local-copy`.
6. **Seed memory.** If `memory/target-<target>.md` exists here, copy it to the workspace `memory/` and add its line to the workspace `MEMORY.md`.
7. **Start the agent in herdr** (see memory `herdr-cli-facts`). Use session `orchard`. Set `session: orchard` and `agent_name: <task>` in the task file.
   ```bash
   herdr --session orchard status server      # if no server: setsid nohup herdr --session orchard server > ~/.orchard-herdr.log 2>&1 < /dev/null &
   herdr --session orchard workspace create --cwd W --no-focus --label <task>   # read .result.root_pane.pane_id
   herdr --session orchard agent start <task> --kind <agent> --pane <pane_id>
   herdr --session orchard agent prompt <task> "Read README.md § Project Scope and CLAUDE.md. Then do the task in autonomous long-run mode."
   ```
   Never run bare `herdr`: it opens the TUI.
   For `runner: local`, the master usually runs inside the local `orchard` session, so the server is already running: skip the start. The worker gets its own workspace (`--no-focus`), so the master pane does not change.
8. **Record.** Set `status: running` in the task file. Add a worklog entry with the task, target, runner, workspace, and harness commit.
   After the worker's first job runs, check that the compute node sees `W` (and `datadir`). Record the result in `memory/target-<target>.md`.
