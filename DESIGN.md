# orchard design

Status: agreed with the user on 2026-11-11. Not yet run on real machines.

## 0. Goal

A **master agent** on the local machine plans, publishes, and monitors tasks.
A task runs in a coding agent inside herdr on a remote machine. If a remote
machine often kills agents, the agent runs on the local machine and does its
work on the remote through SSH.

## 1. No code

The master is an agent. It can run `ssh` and `herdr` itself. So orchard is a
harness repo, not a program: a machine list, a task directory, three Claude
Code skills (`/publish`, `/check`, `/fallback`), and `CLAUDE.md`. Skills load
only when used, so `CLAUDE.md` stays short. Add a script only when the same command fails again and again.

## 2. Machine list: `targets.yaml`

One entry per machine. Three facts: its name, how to get in, and where the
agent runs.

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

Machine types seen so far:

| Type | Get in | Agent can run |
|---|---|---|
| A: direct node | `ssh node` | on the node, or local |
| B1: jumper that can run agents | `ssh jumper`, then the scheduler | on the jumper, or local |
| B2: jumper for scheduler commands only | same | local only |

Config goes in `targets.yaml`. Reasons and quirks go in memory (section 8).

## 3. Task: `tasks/<task>.md`

One file per task. The task name is a short, unique, kebab-case code name. It
is also the workspace directory name.

```yaml
---
task: moe-nan-debug
target: corp
runner: local
agent: claude
workspace: local:~/myworks/moe-nan-debug   # where the harness is
remote_dir: ~/myworks/moe-nan-debug        # runner: local only
harness: 1cc55ca                           # harness commit used
status: running        # planned | running | blocked | idle | killed | done
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

### 4a. Make the workspace

The workspace is a copy of `qhan2012/harness` at `~/myworks/<task>/`, on the
side where the agent runs.

```bash
test -e ~/myworks/<task> && echo EXISTS      # if it exists: stop, tell the person
git clone --depth 1 https://github.com/qhan2012/harness ~/myworks/<task>
git -C ~/myworks/<task> rev-parse --short HEAD   # record in the task file
rm -rf ~/myworks/<task>/.git                 # so nothing is pushed to qhan2012/harness
```

Code repos for the task go in `codebases/`, as the harness says.

### 4b. Write the plan

The master fills `README.md § Project Scope` in the workspace: goal, success
criteria, verifier, scope boundary, constraints. The harness `CLAUDE.md`
already tells the agent to read this section first.

### 4c. Start the agent

The prompt is short, because the plan is in the file:

> Read `README.md § Project Scope` and `CLAUDE.md`. Then do the task in autonomous long-run mode.

An agent that restarts reads the same files and continues.

### Runner `local`

The harness follows the agent. With `runner: local`, the harness is on the
local machine only. The remote has a plain work directory with the same path.

| | Local `~/myworks/<task>/` (harness) | Remote `~/myworks/<task>/` (plain) |
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
- Remote dir: ~/myworks/<task>
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

A check uses two signals. Both runners use the same commands; `runner: herdr`
adds the `enter` prefix.

1. **Agent state in herdr**: `herdr agent list`, and `herdr agent read` when
   needed. A local agent also runs inside a local herdr.
2. **Harness files in the workspace**: the last entries of
   `reports/<date>_worklog.md`, and whether `reports/<date>_summary.md`
   exists. The harness writes the summary only at the end, so **summary
   exists = done**.

| Status | Condition | Master does |
|---|---|---|
| `running` | agent is there and working | nothing |
| `done` | summary exists | read it, report, collect memory (section 8) |
| `blocked` | herdr says blocked, or worklog has `BLOCKER:` | read the screen or worklog, report. Never approve for the person |
| `killed` | agent is gone or herdr is unreachable, and no summary | restart, `kills += 1` |
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

## 6. Fallback

When `kills` reaches 2 (default; the person can also say so at any time), the
master moves the task to `runner: local`: it makes the local harness, adds the
`### Remote` block, copies the remote worklog and memory back, and starts a
local agent that continues. It also sets the machine's default `runner` to
`local` in `targets.yaml` and records the reason in memory.

## 7. Repo layout

```
orchard/
├── DESIGN.md
├── CLAUDE.md             # master rules
├── README.md
├── targets.yaml          # machine list (gitignored; see targets.example.yaml)
├── tasks/                # one <task>.md per task; TEMPLATE.md
├── .claude/skills/       # publish, check, fallback
├── memory/ + MEMORY.md
└── reports/
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
   - *Up, at done*: read the task `MEMORY.md`. Move only lessons that hold
     across tasks into master memory (mostly into `target-<name>.md`).

## 9. Not in scope

A Python package, a ledger, a fleet board, cross-model review, digests,
budgets, automatic memory search. Add one only when a real need shows up.

## Open points

- herdr inside a scheduler job (agent on a compute node). Today the agent
  runs on the `enter` machine or locally, and uses the scheduler from there.
- The real `job_exec` command of the in-house scheduler.
- Nothing here is verified on a real machine yet.
