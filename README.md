# orchard

Orchestration for agents: a light control plane for a **master agent**. The master runs on your local machine. It can:

- check SSH nodes (load, memory, GPU, herdr),
- submit and manage Slurm jobs. The local machine has no Slurm, so every Slurm command runs on the cluster **head node** over SSH,
- start and control [herdr](https://github.com/ogulcancelik/herdr) sessions on a plain node or inside a Slurm job,
- run a **fleet** of agents across all those targets with one person in the loop: a board sorted by who needs you, change events with notifications, different-model review of each builder, a digest, and cleanup of only what orchard started.

```
local (master agent) ──ssh──► head node ── sbatch / squeue / sacct / scancel
        │                         │
        │                         └─ srun --jobid=J --overlap ─► compute node: herdr server + agents
        └──ssh──► plain node ─► herdr server + agents
```

The Python package and CLI are named `orchardctl`. The name `orchard` on PyPI belongs to an unrelated project, which also claims the `orchard` import and CLI.

## Quick start

```bash
pip install -e '.[dev]'
cp inventory.example.yaml inventory.yaml      # edit hosts; keep ProxyJump etc. in ~/.ssh/config
ssh -o BatchMode=yes <head> true              # orchard never prompts for a password
pytest -q                                     # offline tests (fake transport)

orchardctl node box1
orchardctl slurm hpc1 queue
orchardctl slurm hpc1 launch-herdr --opt time=02:00:00 --wait 600   # -> job_id
orchardctl herdr --cluster hpc1 --job <id> start rev --kind claude --cwd '~/proj'
orchardctl herdr --cluster hpc1 --job <id> prompt rev "Run the tests and report." --timeout-ms 600000
orchardctl herdr --cluster hpc1 --job <id> read rev --lines 200
orchardctl slurm hpc1 cancel <id>

# fleet loop (runbooks/fleet.md)
orchardctl herdr --cluster hpc1 --job <id> start bld --kind claude --cwd '~/proj' --run alpha
orchardctl fleet                                   # every agent, most urgent first
orchardctl watch                                   # one JSON event per change + fleet.notify
orchardctl herdr --cluster hpc1 --job <id> review bld --base origin/main   # codex reviews claude
orchardctl digest --notify                         # state/digests/<date>.md for the person
orchardctl cleanup && orchardctl cleanup --yes     # dry run, then stop what orchard started
```

Every command prints JSON on stdout. On an error, it prints `{"error", "message"}` on stderr and exits with code 1. See `runbooks/` for the standard procedures.

## Layout

```
.
├── src/orchardctl/
│   ├── transport.py   # SSHTransport (system OpenSSH), SrunTransport (into a running job via head)
│   ├── inventory.py   # load + check inventory.yaml
│   ├── slurm.py       # SlurmAdapter: submit / queue / job / cancel / wait_running; ownership tag
│   ├── herdr.py       # HerdrClient: server up/down/status, agents, start, prompt, wait, read, keys
│   ├── ledger.py      # state/ledger.jsonl: what orchard started (targets, agents, roles, run code name)
│   ├── fleet.py       # board across targets, attention order, watch events, notify, digest, review prompt
│   └── cli.py         # orchardctl entry point (JSON out)
├── tests/             # offline tests with a fake transport
├── runbooks/          # procedures the master agent follows
├── inventory.example.yaml
├── reports/           # YYYY-MM-DD_worklog.md + _summary.md
├── memory/ + MEMORY.md
├── state/             # runtime state (gitignored): ledger.jsonl, events.jsonl, watch.last.json, digests/
└── CLAUDE.md          # canonical agent instructions (AGENTS.md, .cursorrules point here)
```

## Project Scope

**Goal.** A master agent can bring up, watch, drive and tear down remote coding-agent sessions (herdr) on SSH nodes and Slurm clusters from one local machine, safely and reproducibly.

**Success criteria.**
1. From a clean checkout and a valid inventory, `launch-herdr`, then `herdr start`, then `prompt`, then `read`, then `cancel` works end to end on a real cluster.
2. orchard never cancels or kills a job or process it did not start, unless a person confirms it (`--force`).
3. Each action is one auditable shell command (`-v` logs it).
4. One person can supervise up to `fleet.max_agents` agents across all targets: `fleet` shows who needs them first, `watch` tells them when that changes, and every builder gets a review from a different model before a person merges.

**Verifier.** `pytest -q` (offline). `runbooks/smoke-test.md` on a real head node (online).

**Scope boundary.**
- In scope: SSH nodes, Slurm through the head node, herdr CLI control, the fleet loop (`fleet`, `watch`, `review`, `digest`, `cleanup`).
- Out of scope: other schedulers (PBS, LSF, K8s), a background daemon (`watch` is a foreground loop or a cron job), a web UI, installing herdr on targets, changing cluster configuration, and merging code (a person merges).

**Constraints.**
- Local machine has no Slurm.
- Python ≥ 3.10.
- The only runtime dependency is PyYAML.
- SSH uses the system `ssh`, so `~/.ssh/config` applies as is.
