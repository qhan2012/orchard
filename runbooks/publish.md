# Publish a task

`E` is the target's `enter` command. With `runner: herdr`, the workspace is on the target: put `E` in front of each workspace command. With `runner: local`, the workspace is local: run the commands as they are.

1. **Plan.** Copy `tasks/TEMPLATE.md` to `tasks/<task>.md`. Fill the header and the plan. Publish only after the person accepts the plan.
2. **Check the target.** `ssh -o BatchMode=yes <host> true` must pass. If it fails, tell the person. Do not try to bypass it.
3. **Make the workspace** (DESIGN.md 4a).
   ```bash
   test -e ~/myworks/<task> && echo EXISTS     # EXISTS: stop and tell the person
   git clone --depth 1 https://github.com/qhan2012/harness ~/myworks/<task>
   git -C ~/myworks/<task> rev-parse --short HEAD    # write to `harness:` in the task file
   rm -rf ~/myworks/<task>/.git
   ```
   With `runner: local`, also make the remote work directory: `E 'test -e ~/myworks/<task> && echo EXISTS || mkdir -p ~/myworks/<task>'`.
4. **Write the plan.** Replace the `_TODO_` line under `## Project Scope` in the workspace `README.md` with the five plan items. With `runner: local`, add the `### Remote` block (DESIGN.md 4).
   To write a remote file: `E 'cat > ~/myworks/<task>/README.md' < local-copy`.
5. **Seed memory.** If `memory/target-<target>.md` exists here, copy it to the workspace `memory/` and add its line to the workspace `MEMORY.md`.
6. **Start the agent in herdr** (see memory `herdr-cli-facts`).
   ```bash
   herdr --session orchard status server      # if no server: setsid nohup herdr --session orchard server > ~/.orchard-herdr.log 2>&1 < /dev/null &
   herdr --session orchard workspace create --cwd ~/myworks/<task> --no-focus --label <task>   # read .result.root_pane.pane_id
   herdr --session orchard agent start <task> --kind <agent> --pane <pane_id>
   herdr --session orchard agent prompt <task> "Read README.md § Project Scope and CLAUDE.md. Then do the task in autonomous long-run mode."
   ```
   Never run bare `herdr`: it opens the TUI.
7. **Record.** Set `status: running` in the task file. Add a worklog entry with the task, target, runner, workspace, and harness commit.
