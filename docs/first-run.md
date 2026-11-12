# First run

About 15 minutes. Do this once before the first real task, and again after a herdr or Claude Code upgrade. Each step checks one thing that this repo knows only from docs or source. If a result is different, change the file in the last column, and record the fact in memory with `(verified <date>, first-run)`.

Use one direct SSH node (type A) that has herdr and one agent CLI. Use a throwaway task name such as `first-run`.

| # | Do | Expect | If different, change |
|---|---|---|---|
| 1 | `herdr --session orchard`, then in its first pane `cd <orchard> && claude` | Claude Code starts in the TUI | `README.md` quick start |
| 2 | Type `/` | `/publish`, `/check`, `/close`, `/fallback`, `/adopt` are listed | frontmatter of `.claude/skills/*/SKILL.md` |
| 3 | Ask: "What is your herdr agent name?" | The master ran `herdr agent rename "$HERDR_PANE_ID" master`, and `herdr --session orchard agent list` shows `master` | `CLAUDE.md` "Do not stop your own server"; memory `herdr-cli-facts` (`$HERDR_SESSION`) |
| 4 | Ask: "Run `herdr session stop default`." | Claude Code asks you first, with the reason "orchard guard". Answer no | `.claude/settings.json`, `.claude/hooks/guard.py`; check `python3` and the Claude Code version (`onFailure` needs v2.1.295) |
| 5 | Ask: "Run `herdr --session orchard agent send-keys master enter`." | Denied by the guard | same as 4 |
| 6 | Ask: "Is `<node>` reachable, and which herdr version does it have?" | A subagent runs the `ssh`; you get one line. The version is 0.8.2 | `CLAUDE.md` "Short and read-only"; if the version differs, check the commands in the skills against it |
| 7 | "Experiment on `<node>`: write the hostname and the date to `experiments/hello.txt`, then write the summary. Task name `first-run`." | A launch card, then the plan, then the directory review with disk use. Nothing is made before you agree | `.claude/skills/publish/SKILL.md` steps 0 to 3 |
| 8 | Agree. Watch the workspace step | `<workdir>/first-run/` exists on the node, has `CLAUDE.md`, has no `.git`. The task file has the full harness sha | `/publish` step 4; `HARNESS` |
| 9 | Watch the agent start | If the agent asks a first-start question: the master reports `blocked`, sends no keys, and asks you to answer in the TUI. Write down what it asked | `/publish` step 7 "First-start dialog"; later `agent_args` in `targets.yaml` |
| 10 | After the prompt, open the TUI on the node: `herdr --remote <node> --session orchard` | The agent got the whole prompt as one message, starting with "Read README.md". It is working | `CLAUDE.md` "Quote remote commands"; `/publish` step 7 |
| 11 | "Check first-run." Then again when the agent stops | First `running`, then `done` with the summary. The JSON of `agent list` has `name`, `agent`, `agent_status`, `cwd` | `/check`; memory `herdr-cli-facts` |
| 12 | "Close first-run." | `agent_session` is recorded or reported as absent. `reports/tasks/first-run/` has the copied files. The agent's herdr workspace is closed, the directory stays, and `git status` shows no new tracked file | `/close`; `.gitignore` |

Afterwards, remove the throwaway directory on the node yourself, or tell the master to remove it.

Not covered here: fallback, adopt, research tasks, a scheduler. Try each one the first time you need it, with a small task.
