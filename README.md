# orchard

A harness for a **master agent**. The master runs on your local machine. It plans, publishes, and monitors tasks. Each task runs in a coding agent inside [herdr](https://github.com/ogulcancelik/herdr) on a remote machine, in a workspace made from [qhan2012/harness](https://github.com/qhan2012/harness). If a remote machine often kills agents, the agent runs locally and works on the remote through SSH.

There is no program here. The master uses `ssh` and `herdr` directly and follows three Claude Code skills. Read `DESIGN.md` for the full design.

## Quick start

```bash
cp targets.example.yaml targets.yaml     # edit; keep ProxyJump etc. in ~/.ssh/config
ssh -o BatchMode=yes <host> true         # the master never answers a password prompt
```

Start the master inside herdr, so the master and local workers share one session and herdr tells you when any of them needs you:

```bash
herdr --session orchard                  # opens the TUI; in its first pane:
cd <orchard checkout> && claude          # the master names itself `master` at start
```

Then tell the master what to do, for example:

- "Plan a task on `box1`: find why the MoE run gives NaN." → `/publish`
- "Check all tasks." → `/check`
- "Check `moe-nan-debug` every 10 minutes until done." → `/loop 10m /check moe-nan-debug`
- "Close `moe-nan-debug`." → `/close`
- "Run this task locally instead." → `/fallback`
- "Take over the long run I started on `box1` in pane w2:p1." → `/adopt`

## Layout

```
.
├── DESIGN.md             # the design, section by section
├── HARNESS               # pinned harness repo + commit used for every task workspace
├── CLAUDE.md             # master rules (AGENTS.md, .cursorrules point here)
├── targets.yaml          # machine list (gitignored; see targets.example.yaml)
├── tasks/                # one <task>.md per task; TEMPLATE.md
├── .claude/skills/       # publish, check, close, fallback, adopt (the procedures)
├── memory/ + MEMORY.md   # target-<name>.md per machine; entries end with (verified date, source)
└── reports/              # YYYY-MM-DD_worklog.md + _summary.md
```

## Project Scope

**Goal.** From one local machine, a master agent plans, publishes, and monitors agent tasks on remote machines, and moves a task to a local agent when the remote kills agents.

**Success criteria.**
1. Publish: after the person reviews the directory and its disk use, a task gets a workspace at `<workdir>/<task>/` (default `~/myworks/<task>/`) made from the harness, with the plan in `README.md § Project Scope`, and an agent that starts from it.
2. Monitor: a check gives the right status (`running`, `done`, `blocked`, `idle`, `killed`) from herdr and the workspace files.
3. Fallback: after two kills, the task continues with a local agent from the last worklog entry.
4. The master never stops or changes something it did not start, unless a person confirms it.

**Verifier.** Run one real task through publish, check, and done on a direct node. Then one through fallback.

**Scope boundary.**
- In scope: the machine list, task files, skills, memory.
- Out of scope: any code (see `DESIGN.md` 9), installing herdr or agents on targets, changing cluster configuration, merging code.

**Constraints.**
- The local machine has no scheduler. Scheduler commands run on the head or jumper.
- SSH uses the system `ssh`, so `~/.ssh/config` applies as is.
