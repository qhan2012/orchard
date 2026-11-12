# orchard design

Status: agreed with the person on 2026-11-11. Not yet run on real machines.

## 0. Goal

A **master agent** on the local machine plans, publishes, and monitors tasks.
A task runs in a coding agent inside herdr on a remote machine. If a remote
machine often kills agents, the agent runs on the local machine and does its
work on the remote through SSH. The master can also take over an agent that
the person started by hand.

## 1. No code (one exception: section 10)

The master is an agent. It can run `ssh` and `herdr` itself. So orchard is a
harness repo, not a program: a machine list, a task directory, five Claude
Code skills (`/publish`, `/check`, `/close`, `/fallback`, `/adopt`), and
`CLAUDE.md`. Skills load only when used, so `CLAUDE.md` stays short. Add a
script only when the same command fails again and again.

## 2. Machine list: `targets.yaml`

One entry per machine. An entry is a **target**. Three required facts: its
name, how to get in, and where the agent runs.

```yaml
box1: {enter: "ssh box1", runner: herdr}
corp: {enter: "ssh jumper", job_exec: "myrun --job {job} --", runner: local}
```

- `enter`: the command prefix that runs a command on the machine.
- `job_exec` (optional): the command on that machine that runs a command
  inside a scheduler job. Slurm: `srun --jobid={job} --overlap`. An in-house
  scheduler has its own.
- `runner`: `herdr` (agent on the machine) or `local` (agent on the local
  machine, works through `enter`).
- `agent` (optional): the default agent kind for agents that run there.
- `agent_args` (optional): per kind, native CLI arguments for the start.
- `workdir` (optional): where workspaces go, `<workdir>/<task>`. Default
  `~/myworks`. It always ends in `myworks`.
- `datadir` (optional): a place for large outputs, when the only big disk is
  purged.

Machine types seen so far:

| Type | Get in | Agent can run |
|---|---|---|
| A: direct node | `ssh node` | on the node, or local |
| B1: jumper that can run agents | `ssh jumper`, then the scheduler | on the jumper, or local |
| B2: jumper for scheduler commands only | same | local only |

One more entry, `local`, is this machine. It has no `enter`. It holds the
default `agent` and `agent_args` for agents that run locally.

Config goes in `targets.yaml`. Reasons and quirks go in memory (section 8).

## 3. Task: `tasks/<task>.md`

One file per task. The task name is a short, unique, kebab-case code name. It
is also the workspace directory name.

```yaml
---
task: moe-nan-debug
kind: experiment       # experiment | research (4e)
target: corp
runner: local
agent: claude
started_by: orchard    # orchard | person (adopted)
session: orchard       # herdr session of the agent
agent_name: moe-nan-debug
agent_session:         # native session id, written at close
workspace: local:/home/qh/myworks/moe-nan-debug   # where the harness is (absolute path)
remote_dir: /proj/qh/myworks/moe-nan-debug        # runner: local only
harness: fc24f243b4e0d96198daf6cfe5a971bc7b7fd9de   # full harness sha used
status: running        # planned | running | blocked | idle | killed | done | closed
kills: 0
check: every 10m       # set at runtime; empty = only when asked
last_checked: 2026-11-11T21:40
latest: iteration 3, reproducer down to 40 lines
---
```

The body holds the plan draft. After publish, the plan in the workspace
`README.md` is the source of truth. The task file is the index of where
everything is.

## 4. Publish

### 4a. Choose and review the directory

Where workspaces go is a property of the machine: `workdir` in
`targets.yaml`, chosen once with the person on first use. Order of
preference: (1) a disk that is not purged and that compute nodes can see;
(2) home, if the quota is enough; (3) if only a purged disk has space, the
workspace stays in home and that disk becomes `datadir` for large outputs.
The worklog and memory are the recovery state of a task, so they do not go
on a purged disk. Home must always keep free space: agents and herdr write
their state there.

**For every new workspace, the person reviews before the master makes it**:
the directory, the disk use of home and `workdir`, and the alternative
disks. Commands cannot show everything (`df` on a shared filesystem shows
the whole filesystem, not the person's quota; purge policy; file-count quota;
what compute nodes see), so the master asks once and records the answers in
`memory/target-<name>.md`.

### 4b. Make the workspace

`W` is the workspace directory, `<workdir>/<task>`.

The workspace is a copy of `qhan2012/harness` at `W`, on the side where the
agent runs. The harness version is pinned in the `HARNESS`
file (repo URL and full commit sha), not the latest main. So all tasks in a
batch get the same rules, and an upgrade is a one-line PR that a person
reviews.

```bash
test -e W && echo EXISTS      # if it exists: stop, tell the person
git init -q W
git -C W fetch -q --depth 1 <url> <sha>   # from HARNESS
git -C W checkout -q FETCH_HEAD
git -C W rev-parse HEAD       # must equal <sha>; record in the task file
rm -rf W/.git                 # so nothing is pushed to qhan2012/harness
```

`HARNESS` also records which harness commit orchard's own `CLAUDE.md` is
based on, so a harness upgrade shows which master rules to sync.

Not used: a git submodule (orchard needs no harness files locally) or a
vendored copy (a second copy that drifts, and must be sent to the remote).

Code repos for the task go in `codebases/`, as the harness says.

### 4c. Write the plan

The master fills `README.md § Project Scope` in the workspace: goal, success
criteria, verifier, scope boundary, constraints. The harness `CLAUDE.md`
already tells the agent to read this section first. Two constraints are
always there: every scheduler job name starts with `<task>-`, and the worker
cancels its jobs before it writes the summary.

### 4d. Start the agent

The prompt is short, because the plan is in the file:

> Read `README.md § Project Scope` and `CLAUDE.md`. Then do the task in autonomous long-run mode.

An agent that restarts reads the same files and continues.

### 4e. Task kinds

Every task has its own workspace made from the harness. Two kinds:

| `kind` | For | Agent and workspace | Remote access |
|---|---|---|---|
| `experiment` | run, build, or debug on one target | on the target, or local with a `### Remote` block | read and write on that target |
| `research` | a deep dive across targets with web search: analysis, comparison, report | local (`target: local`, `runner: local`) | read-only on every listed target |

A research worker runs locally because the local machine has web access,
the work belongs to no single target, and a long session is safest there.
The master knows where each task's workspace is (`tasks/*.md`; closed tasks
have a local copy in `reports/tasks/`), so it writes the places to read into
the plan:

```markdown
### Remotes (read-only)
- corp: ssh jumper — /proj/qh/myworks/moe-nan-debug
- box1: ssh box1 — /home/qh/myworks/moe-baseline
- local copy: <orchard>/reports/tasks/moe-sweep
- Rules:
  - Read only. Do not run jobs, and do not change or make files on a remote.
  - Copy only small files (reports, metrics). Do not copy checkpoints or datasets.
  - If the analysis needs a new experiment, write the request in the report. Do not run it.
```

A new experiment that the research asks for is a separate `experiment`
task. The person decides, and the master publishes it. So analysis and
changes to remote state stay in different agents.

To start the right kind, the master does not guess. It shows the person a
launch card first (task, kind, where the agent runs, workspace, remotes,
goal) and waits. If the request does not say the kind, it asks.

### 4f. Agent kind

Which CLI runs the worker (herdr `--kind`: `claude`, `codex`, `cursor`,
...) is decided in this order: (1) what the person says in the request;
(2) the `agent` of the entry where the agent runs, in `targets.yaml`;
(3) `claude`. The launch card shows it, so the person can change it.

Before the start, the master checks on that machine that the CLI is
installed (`command -v`; `cursor` is `cursor-agent`). Login is asked once
per machine and kind, and recorded in memory. If either fails, the master
stops. It does not change the kind itself.

What changes with the kind:
- Rules: nothing. The harness has `AGENTS.md` and `.cursorrules`, which
  point to `CLAUDE.md`.
- Permissions for unattended runs: each CLI has its own flags. They go in
  `agent_args` per kind, chosen by the person, and herdr passes them after
  `--`. Without them, a long task can stop at approval prompts (`blocked`).
- Resume after close: herdr 0.8.2 can resume `claude`, `codex`, and
  `cursor` from a session id, if its integration reported one.

The master itself needs Claude Code, because it uses skills and `/loop`.
Workers do not.

### Runner `local`

The harness follows the agent. With `runner: local`, the harness is on the
local machine only. The remote has a plain work directory,
`<remote workdir>/<task>`.

| | Local workspace (harness) | Remote work directory (plain) |
|---|---|---|
| `README.md`, `CLAUDE.md`, `MEMORY.md`, `memory/`, `reports/` | yes | |
| `codebases/` | `REPOS.md` only | the code |
| `experiments/` | small results (metrics, summaries) | run directories, full logs |

The master adds this block under Constraints in the local `README.md`:

```markdown
### Remote
- Target: corp
- Enter: ssh jumper
- Job exec: myrun --job {job} --
- Remote dir: <remote workdir>/<task>
- Rules:
  - Run every build, test, and experiment on the remote, through Enter.
  - Code and full logs stay on the remote. Do not copy large files to local.
  - Write reports and memory locally only.
  - Do not touch anything outside Remote dir without permission.
```

A `runner: herdr` task has no such block, so the agent knows it works on its
own machine. The harness itself does not change.

Known cost: a local agent edits remote code through SSH only. If this hurts,
add "edit locally, `rsync` to the remote" later.

## 5. Monitor

A check covers the open tasks: `running`, `blocked`, `idle`, `killed`. It
uses two signals. Both runners use the same commands; `runner: herdr` adds
the `enter` prefix.

1. **Agent state in herdr**: `herdr agent list`, and `herdr agent read` when
   needed. A local agent also runs inside a local herdr.
2. **Harness files in the workspace**: the last entries of
   `reports/<date>_worklog.md`, and whether `reports/<date>_summary.md`
   exists. The harness writes the summary only at the end, so **summary
   exists = done**.

| Status | Condition | Master does |
|---|---|---|
| `running` | agent is there and working | nothing |
| `done` | summary exists and the agent does not work | read it, report. The agent stays, for follow-up questions |
| `blocked` | herdr says blocked, or worklog has `BLOCKER:` | read the screen or worklog, report. Never approve for the person |
| `killed` | the target is reachable, the agent is gone, and no summary | restart, `kills += 1`. Adopted agent: report only |
| (unreachable) | `ssh` fails | not a status. Keep the old status, report. No kill count, no restart |
| `idle` | agent is there but stopped, no summary | read the screen, decide what it waits for |

Restart after a kill: start the agent again with the same short prompt plus
"Read the worklog first and continue from the last entry." The plan is in the
README and the progress is in the worklog, so no session restore is needed.

**When and how often to check is decided at runtime**, by the person ("check
now", "check this task every 10 minutes until done"). A cadence runs as
`/loop <interval> /check <task>` in the master session. `/loop` stops when the
session ends, so the master also records the cadence in the task file
(`check:`) and, after a restart, tells the person which loops to start again.
With no cadence, it checks only when asked.

## 5a. Close

`done` and `closed` are different. At `done` the master only reports. The
person closes a task when they have no more questions. Then the master:
records the agent's native session id if herdr reports one (so the
conversation can be resumed), checks that no scheduler job named
`<task>-*` is left, copies `reports/` and memory back to the local machine,
collects memory (section 8), and closes the worker's herdr workspace. The
workspace directory stays.

The master does not stop herdr servers. A server belongs to a machine, not
to a task, and an idle server costs almost nothing. It stops one only when
the person asks, after it shows what still runs there. For an adopted
agent, close only copies the record and collects memory. It does not touch
the agent.

## 6. Fallback

When `kills` reaches 2 (default; the person can also say so at any time), the
master moves the task to `runner: local`: it makes the local harness (with
the directory review of 4a), adds the
`### Remote` block, copies the remote worklog and memory back, and starts a
local agent that continues. It also sets the machine's default `runner` to
`local` in `targets.yaml` and records the reason in memory. An adopted task
moves only when the person asks. If the remote agent still runs, the master
asks before it closes it.

## 6a. Master inside herdr

The master can run in a pane of the local herdr session `orchard`, as the
agent named `master`. Then local workers (`runner: local`) are in the same
session: one TUI shows all of them, and herdr marks any pane that is done or
blocked, including the master. Remote workers stay in the herdr server on
their machine; the master reaches them through `enter`. (`herdr --remote
<host>` attaches the TUI to one remote server at a time.)

Two rules follow: `/check` skips the agent `master`, and the master never
stops the `orchard` server, because it runs in it.

## 6b. Adopt a running agent

The person can start a long-run agent by hand and then give it to the
master. `/adopt` finds the agent (machine, herdr session, name or pane),
names it if it has no name, and writes a task file with
`started_by: person`. The task file also stores the agent's `session` and
`agent_name`, because a hand-started agent is often in the default session.

An adopted agent stays the person's. The master checks it and reads it, but
prompts, restarts, stops, or moves it only when the person asks. Its
directory may not be a harness workspace. Then a check uses the herdr state
and the screen only, and only the person says the task is done. The master
adds no harness files to that directory unless the person asks.

## 7. Repo layout

```
orchard/
├── DESIGN.md
├── HARNESS               # pinned harness repo + commit for task workspaces
├── CLAUDE.md             # master rules
├── README.md
├── targets.yaml          # machine list (gitignored; see targets.example.yaml)
├── tasks/                # one <task>.md per task (gitignored); TEMPLATE.md
├── .claude/skills/       # publish, check, close, fallback, adopt
├── .claude/hooks/        # guard.py: three hard rules (section 10)
├── memory/ + MEMORY.md   # target-*.md are gitignored
├── reports/              # gitignored: worklogs; tasks/<task>/ = records copied back at close
└── docs/history/         # worklogs of the design work (no site data)
```

## 8. Memory

Base: the harness memory (`memory/<name>.md` with frontmatter, index in
`MEMORY.md`). Three additions for the master:

1. **One file per machine**: `memory/target-<name>.md` holds what the machine
   is like: kills agents or not, scheduler traps, herdr version, where tools
   are.
2. **Evidence on each entry**: every entry ends with
   `(verified YYYY-MM-DD, <source>)`. Machine facts go stale fast.
3. **Two transfers between the master and a task**:
   - *Down, at publish*: copy `memory/target-<name>.md` into the new
     workspace `memory/` and add its index line, so the worker knows the
     machine from the start.
   - *Up, at close*: read the task `MEMORY.md`. Move only lessons that hold
     across tasks into master memory (mostly into `target-<name>.md`).

## 9. Not in scope

A Python package, a ledger, a fleet board, cross-model review, digests,
budgets, automatic memory search, hooks beyond the three in section 10. Add one only when a real need shows up.

## 10. Guard hook

Most rules need judgment, so they stay instructions. A hook is used only
where a mistake is costly, cannot be undone, and shows in the command text:

| Command | Decision | Why |
|---|---|---|
| `herdr ... agent send-keys` / `pane send-keys` | deny | this is how an approval dialog gets answered for the person |
| `herdr ... server stop` / `session stop` | ask the person | it ends every agent in that server |
| `git add -f` / `--force` | deny | it can publish gitignored site data from this public repo |

`.claude/settings.json` registers `.claude/hooks/guard.py` as a `PreToolUse`
hook for Bash. The script needs `python3`. `"onFailure": "block"` makes a
broken hook stop the command instead of letting it pass; this needs Claude
Code v2.1.295 or later.

The hook matches text. A command hidden in a script file gets past it. It
guards against a slip by the master, and it is not a security boundary. It
does not apply to workers.

## Open points

- herdr inside a scheduler job (agent on a compute node). Today the agent
  runs on the `enter` machine or locally, and uses the scheduler from there.
- The in-house scheduler: its real `job_exec` command, and how to list jobs
  by name prefix at close. Deferred.
- herdr version: the skills are checked against herdr 0.8.2 (source and docs
  at tag `v0.8.2`), the version in use. Not yet run against a live herdr.
- Nothing here is verified on a real machine yet.

## Known limits

- A hook enforces three rules only, in the master session (section 10).
  All other rules, and every rule for workers (for example "read-only" for
  research workers), are instructions. No hook or sandbox enforces them.
- A remote agent needs network access to its model API. A target without it
  must use `runner: local`. Record this in the target's memory.
- Login of an agent CLI cannot be checked by a command; the master asks.
  Without `agent_args`, a long task can stop at approval prompts.
- Resume after close needs the herdr integration of that agent on that
  machine.
- `/loop` ends with the master session. The master offers to start loops
  again at the start of a session.
- A local-runner agent edits remote code through SSH only.
- Site data is gitignored (public repo), so it has no git backup.
