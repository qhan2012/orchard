# 2026-11-11 worklog

## 1. Rewrite from scratch: design and skeleton
- Context (from user): v0.1 (Python `orchardctl`) and the later branches (PR #3 fleet loop, PR #4 exec/check) are over-engineered. Rewrite from scratch, grown from real needs.
- User needs: a local master plans, publishes, and monitors tasks. Tasks run in remote herdr. Machines are direct SSH nodes, or clusters behind a jumper with Slurm or an in-house Slurm-like scheduler. Some jumpers can run agents, some only scheduler commands. If the remote often kills agents, run the agent locally and work through SSH.
- Design walk-through with the user, section by section. Result: `DESIGN.md`.
- DECISION (user): no code. The master is an agent and runs `ssh` and `herdr` itself.
- DECISION (user): the workspace is `~/myworks/<task>/`, a copy of qhan2012/harness with `.git` removed. The master records its location in `tasks/<task>.md`.
- DECISION (user): the task plan goes into the workspace `README.md § Project Scope`.
- DECISION (user): with `runner: local`, the harness is local only. The local README gets a `### Remote` block (target, enter, job exec, remote dir, rules).
- DECISION (user): when and how often to check is set at runtime, not in the design.
- DECISION (user): three memory additions: one file per machine, `(verified date, source)` on each entry, and memory transfer down at publish and up at done. The `verified` rule also goes to the harness: qhan2012/harness PR #22.
- Change: removed `src/`, `tests/`, `pyproject.toml`, `inventory.example.yaml`, old runbooks, `state/`, memory `slurm-via-head`. Added `DESIGN.md`, `targets.example.yaml`, `tasks/TEMPLATE.md`, `runbooks/{publish,check,fallback}.md`. Rewrote `README.md` and `CLAUDE.md`. Kept memory `herdr-cli-facts` and added evidence to each entry.
- Not yet verified: everything. The herdr commands in `runbooks/publish.md` come from the herdr source and docs, not from a running herdr. Next: publish one small real task on a direct node.
- Open: the real `job_exec` of the in-house scheduler; herdr inside a scheduler job.

## 2. Claude Code features: skills and /loop
- The person starts the master with Claude Code. Two features fit the design (source: https://code.claude.com/docs/en/features-overview, https://code.claude.com/docs/en/scheduled-tasks):
  - Skills load only their description until used. The three runbooks became `.claude/skills/{publish,check,fallback}/SKILL.md`.
  - `/loop <interval> <prompt>` repeats a prompt, including a skill, while the session is open. A runtime cadence is now `/loop 10m /check <task>`. The task file keeps `check:` because `/loop` ends with the session.
- DECISION (user): not now: subagents per check, hooks, desktop scheduled tasks. Add them after a real task shows the need.
- PR #3 and #4 closed as superseded by #5.

## 3. Pin the harness version
- Problem: `/publish` cloned the latest harness main. Tasks in one batch could get different rules, and a harness change reached the master without review. Example: harness#22 moved main from `1cc55ca` to `fc24f24`.
- Change: new file `HARNESS` (repo URL + full sha `fc24f243b4e0d96198daf6cfe5a971bc7b7fd9de`, plus the harness commit that orchard's own `CLAUDE.md` is based on). `/publish` step 3 fetches that commit. The task file records the full sha. `/fallback` rebuilds the local harness at the task's recorded sha.
- DECISION: no submodule and no vendored copy. Reason: orchard needs no harness files locally, and a copy drifts.
- Verified locally: `git init` + `git fetch --depth 1 <url> <full sha>` + `checkout FETCH_HEAD` gives `HEAD == fc24f24...` and the harness tree (with the #22 `verified` rule). Not yet run on a remote target.

## 4. Align with herdr 0.8.2
- The person uses herdr 0.8.2. Memory `herdr-cli-facts` was written from v0.9.5.
- Checked every herdr command in `/publish` and `/check` against tag `v0.8.2` (`docs/versions/0.8.2/.../cli-reference.mdx`, `src/`): `--session` prefix, `server`, `status server`, `workspace create --cwd --label --no-focus`, `agent start --kind --pane`, `agent prompt`, `agent list`, `agent read --source --lines`. All exist with the same syntax. `agent list` fields and the five `agent_status` values are the same.
- `--session` works on control commands: `src/session.rs` `configure_from_args` removes it before dispatch.
- Difference found: the 0.8.2 docs do not mention SIGHUP handling. No change needed: `/publish` starts the server with `setsid nohup ... &`.
- Change: rewrote memory `herdr-cli-facts` for 0.8.2, each line with `(verified 2026-11-11, v0.8.2 ...)`. `/publish` step 2 now runs `herdr --version` and checks commands again if the version differs. `DESIGN.md` open points name the version.
- Not yet verified against a live herdr.

## 5. Trim master rules
- The master copied some harness rules that are for the worker, not for the master: apple-to-apple comparisons, separate correctness and perf runs, and the autonomous long-run mode section. Each worker already has them in its workspace `CLAUDE.md`.
- DECISION (user): remove them from orchard `CLAUDE.md`. Rules renumbered 1-7. A short `## Worklog` section replaces the long-run mode section: one entry per publish, status change, fallback, or decision.

## 6. Master inside herdr; adopt hand-started agents
- Need (from user): run the master itself in herdr, with its workers in the same herdr. Let the master take over a long-run agent that the person started by hand.
- Facts (herdr v0.8.2 docs and source): `agent rename <target> <name>`; `session list --json`; `--session default` selects the default session (`src/session.rs` `normalize_name`).
- Change:
  - Master in herdr (`DESIGN.md` 6a): run in local session `orchard` as agent `master`. Local workers share the session. Remote workers stay in their own server. `/check` skips `master`. `CLAUDE.md`: never stop the `orchard` server and never prompt `master`. README quick start shows the launch.
  - Adopt (`DESIGN.md` 6b, new skill `/adopt`): find the agent, read it, name it if unnamed, write a task file with `started_by: person`, `session`, `agent_name`. An adopted agent is checked and read only. Prompt, restart, stop, or fallback only when the person asks. A non-harness directory is checked by herdr state and screen only.
  - Task template: `started_by`, `session`, `agent_name`. `/check` uses them instead of the fixed `orchard` session and task name.
- Not yet verified against a live herdr.

## 7. Close a task; choose and review the workspace directory
- Questions (from user): after a task ends, does the agent stop, does herdr stop? Should the master look at disk use and disk servers before it makes a workspace?
- First answer reviewed and corrected:
  - "Stopping the agent loses its context" was too strong: herdr 0.8.2 reports `agent_session` with an official integration, and can resume claude and codex.
  - A `started_server` field per task was wrong: a server belongs to a machine, and `agent list` empty does not prove the server is unused.
  - "Put the whole workspace on scratch" was wrong: the worklog and memory are the recovery state and must not be on a purged disk.
- DECISION (user): `done` only reports and keeps the agent. A new status `closed` and skill `/close` do the cleanup when the person says so. The master does not stop herdr servers unless the person asks.
- DECISION (user): `workdir` (and optional `datadir`) per target in `targets.yaml`, chosen once. For every new workspace, the person reviews the directory, the disk use, and the alternative directories before the master makes it.
- Change: new skill `/close`; `/publish` step 3 (directory review) and job-name constraints in the plan; `/check` done branch; task template (`closed`, `agent_session`, absolute `workspace`); `targets.example.yaml`; `CLAUDE.md` rules; `DESIGN.md` 2, 4a, 5a; memory `herdr-cli-facts` (workspace close, agent_session). Also fixed a stray code fence in `/publish`.
- Open: how to list jobs by name prefix on the in-house scheduler.
- Not yet verified against a live herdr or a real target.

## 8. Proofread and consistency check
- Scope: `README.md`, `CLAUDE.md`, `DESIGN.md`, the five skills, the task template, `targets.example.yaml`, memory. The in-house scheduler is deferred (user).
- Behaviour gaps fixed:
  - `/check` with no argument checked only `running` tasks, so a `blocked` or `idle` task was never checked again. It now checks every open task.
  - `/check` `idle` could answer an adopted agent. It now only reports for `started_by: person`.
  - `/fallback` did not say what to do with a remote agent that still runs. It now asks the person before it closes it.
  - `/close` copied files that an adopted, non-harness directory does not have. It now copies only what exists.
- Stale text fixed: "three skills" (now five) in `README.md` and `DESIGN.md` 1; `DESIGN.md` 3 example lacked `started_by`, `session`, `agent_name`, `agent_session` and used `~` paths; `DESIGN.md` 4b and the local-runner table still used `~/myworks`; `/publish` step 4 pointed to `DESIGN.md` 4a (now 4b); `DESIGN.md` 5a said an adopted agent is never closed, but `/close` handles it; README success criteria and verifier lacked close and adopt.
- Terms: "workspace" is the task directory; herdr's own is always "herdr workspace"; "target" is one entry in `targets.yaml`; "the person", not "the user". Defined in `CLAUDE.md`.
- Mechanical checks passed: every `/skill` reference names an existing skill; step and section references match; code fences are balanced; skill frontmatter and `targets.example.yaml` parse.

## 9. Research tasks; launch card
- Need (from user): a multi-hour deep dive on experiments across servers, with online search. How to run it, and how to start each kind of task without mistakes.
- DECISION (user): add it. A research task has its own workspace from the harness, like every task.
- Change: task field `kind: experiment | research` and `remotes:`. A research worker runs locally (`target: local`), reads the listed targets, and uses web search. Its README gets a `### Remotes (read-only)` block. A new experiment it asks for is a separate `experiment` task. `/publish` step 0 decides the kind and shows a launch card; the person confirms before any other step. `DESIGN.md` 4e, README examples, `CLAUDE.md` hand-off rule.
- Not yet verified on a real target.

## 10. Agent kind per worker
- Need (from user): define which agent CLI (Claude Code, Cursor CLI, Codex) each worker uses.
- Facts (herdr v0.8.2): `agent start --kind` supports `claude`, `codex`, `cursor`; args after `--` go to the CLI; `src/agent_resume.rs` resumes claude, codex, and cursor (`cursor-agent`).
- DECISION (user): order is the person's request, then `agent` of the entry in `targets.yaml` where the agent runs (new `local` entry for this machine), then `claude`. Optional `agent_args` per kind. `/publish` checks that the CLI is installed, asks once about login, and never changes the kind itself. `DESIGN.md` 4f.
- The `agent_args` example for claude in `targets.example.yaml` is a commented example, not a recommendation. The person chooses the permission flags.

## 11. Known issues fixed (2026-11-12)
- Public repo: `tasks/` (except the template), `memory/target-*.md`, and `reports/` are now gitignored. Target memory files are not listed in `MEMORY.md`. The design worklogs moved to `docs/history/`. `CLAUDE.md` has a "Public repo" section.
- `/check`: an unreachable target is not `killed`. No kill count, no restart. The agent's absence is confirmed twice before a restart.
- `/check`: a summary plus a working agent is `running` (work after `done`).
- `/publish`: a target without GitHub access gets the harness copy from the local machine through `tar`.
- Master: renames itself without `--session`; warns if it is not in session `orchard`; offers to restart loops at session start; one master session per checkout.
- Removed unused Python and Node entries from `.gitignore`.
- Not fixed, listed in `DESIGN.md` "Known limits": rules are not enforced by a hook; login check; `agent_args`; resume needs the herdr integration; local-runner edits through SSH.

## 12. Guard hook (2026-11-12)
- Question (from user): can hooks replace rules that are only instructions? Answer: partly. A hook sees the command text, not the intent or who owns a resource.
- DECISION (user): few hooks, only for very useful and clear cases.
- Change: `.claude/hooks/guard.py` + `.claude/settings.json` (`PreToolUse`, Bash). Three rules: deny `herdr ... send-keys`; ask before `herdr ... server stop` / `session stop`; deny forced `git add`. Left out on purpose: `scancel`, `kill`, `rm -r` (they need ownership, which is judgment).
- Source: https://code.claude.com/docs/en/hooks (stdin fields, `hookSpecificOutput.permissionDecision`, `onFailure`, exec form with `args`). Only the first part of that page was read.
- Verified locally: 14 sample commands through the script (7 matched as expected, 7 passed) and a non-Bash event. Not yet run inside Claude Code.

## 13. Small questions and the master's context (2026-11-12)
- Question (from user): many small questions add context to the master. Better practice?
- DECISION (user): `CLAUDE.md`: a short read-only question that needs a command goes to a subagent, and the master keeps only the conclusion. The master's context is disposable, so lasting facts go to files at once. README: a table of habits (`/btw`, just ask, `/clear`, a different session).
- Sources: https://code.claude.com/docs/en/interactive-mode (`/btw`: no history, no tools), https://code.claude.com/docs/en/subagents (own context, returns the summary).

## 14. Remote quoting, first-start dialog, first-run checklist (2026-11-12)
- Red flag 1: the skills wrote `E herdr ... agent prompt <task> "text"`. `ssh` joins its arguments, so the remote shell splits the text. Shown with a stand-in ssh: 10 arguments without the outer quotes, 4 with them. Fix: rule "Quote remote commands" in `CLAUDE.md`; every skill names the remote form; `/publish` step 7 shows a full example.
- Red flag 2: a new workspace directory can make the agent ask a first-start question. Then herdr reports `blocked` and refuses the prompt, and the master may not send keys. Fix: `/publish` step 7 reads the status before the prompt, and on `blocked` asks the person to answer in the TUI. It also checks for `working` after the prompt.
- New `docs/first-run.md`: 12 steps, each checks one assumption that was taken from docs or source only.

## 15. Worker permissions (2026-11-12)
- DECISION (user): research and experiment workers both run in skip-permission mode. The person chooses the master's mode at launch, so the repo sets nothing for the master (no allow list for read-only commands).
- Change: `/publish` uses `--dangerously-skip-permissions` as the default `agent_args` for `claude` workers and shows it on the launch card. `targets.yaml` can replace it per entry and kind. Other kinds have no default.
- Recorded in `DESIGN.md` 4f: a worker can run any command as the person's account; workspace scope and research read-only are instructions only; a research worker reads web pages, which adds a prompt-injection risk. The person accepted this.
- Not added: deny rules such as `git push`. A task's worker may open a PR for its own repo, so a blanket deny would block allowed work.
- Not verified: if skip mode also skips the first-start trust question. `docs/first-run.md` step 9 checks it.

## 16. Publish fixes (2026-11-12)
- Root: `/publish` step 2 runs `id -u`. As root with `--dangerously-skip-permissions` it stops. Basis: recall that Claude Code refuses the flag as root; not checked against docs.
- `MEMORY.md`: the pinned harness (fc24f24) has no `MEMORY.md` (checked with `git ls-tree`). `/publish` step 6 makes it. `/fallback` and `/close` copy only items that exist (`ls -d ... 2>/dev/null` inside the remote command; tested locally).
- One review: the launch card, the plan, and the directory review were three stops. Now steps 0 to 2 only collect, and step 3 shows one screen and waits once. Step numbers did not change.
- Task name: must match herdr's agent name rule `[a-z][a-z0-9_-]{0,31}` (v0.8.2 docs), not be `master`, and not exist. Checked in step 0.
- `docs/first-run.md` step 4: test the guard's `ask` in the master's usual permission mode; if it does not ask, change it to `deny`.

## 17. `/check` runs in a subagent (2026-11-12)
- Problem: each `/loop` round put the check's command output into the master's context. A night of checks fills it.
- Change: `check` has `context: fork` (source: https://code.claude.com/docs/en/skills, frontmatter `context`). It looks, decides, writes `status`, `last_checked`, `latest`, `unreachable` to the task file, and returns at most 8 lines for each task. It does not act and does not ask the person.
- The actions moved to `CLAUDE.md` "After a check", because the master sees only the report, not the skill text: stop the loop, report, answer an idle agent, count kills, restart, `/fallback`.
- New task field `unreachable` (count in a row), so "stop the loop after 3" survives between rounds.
- Not verified: that a forked skill can read and write the task files, and how `/loop` shows its result. `docs/first-run.md` step 11 checks it and names the way back (remove `context: fork`).

## 18. Backup of the site data (2026-11-12)
- Need (from user): after the master starts, the person may give a subfolder of a private GitHub repo to back up the local state.
- Change: new skill `/backup` (`set`, back up, `restore`); location in gitignored `backup.local`; `CLAUDE.md` says when to run it. The master checks that the repo is private and is not the public orchard repo.
- DECISION: `tar`, not `rsync`, because `rsync` is not on every machine (it was absent in the test environment). Backup never deletes; restore uses `tar -k` and never overwrites.
- Verified locally with temporary directories: the backup holds only site data (no template, no `.gitkeep`, no shared memory files); restore brings back a deleted task file and keeps a changed `targets.yaml`. The git and `gh` steps were not run.
