# orchard

Orchestration for agents: a light control plane for a **master agent**. The master runs on your local machine. It can:

- run one command on any target and check it (`exec`, `check`): a direct SSH node, a cluster head/jumper, or inside a running job,
- submit and manage Slurm jobs. The local machine has no Slurm, so every Slurm command runs on the cluster **head node** over SSH,
- start and control [herdr](https://github.com/ogulcancelik/herdr) sessions on a plain node or inside a Slurm job.

```
local (master agent) ──ssh──► head node ── sbatch / squeue / sacct / scancel
        │                         │
        │                         └─ job_exec (srun --jobid=J --overlap, or an in-house tool) ─► compute node
        └──ssh──► plain node ─► herdr server + agents
```

The Python package and CLI are named `orchardctl`. The name `orchard` on PyPI belongs to an unrelated project, which also claims the `orchard` import and CLI.

## Quick start

```bash
pip install -e '.[dev]'
cp inventory.example.yaml inventory.yaml      # edit hosts; keep ProxyJump etc. in ~/.ssh/config
ssh -o BatchMode=yes <head> true              # orchard never prompts for a password
pytest -q                                     # offline tests (fake transport)

orchardctl check box1                          # direct node: load, mem, GPU (rocm-smi/nvidia-smi), herdr, agents
orchardctl check hpc1                          # the head/jumper itself
orchardctl exec box1 -- nproc                  # JSON: rc, stdout, stderr
orchardctl exec corp --job <id> -- 'cd ~/proj && git status'   # inside a job; quote pipes and &&
orchardctl slurm hpc1 queue
orchardctl slurm hpc1 launch-herdr --opt time=02:00:00 --wait 600   # -> job_id
orchardctl herdr --cluster hpc1 --job <id> start rev --kind claude --cwd '~/proj'
orchardctl herdr --cluster hpc1 --job <id> prompt rev "Run the tests and report." --timeout-ms 600000
orchardctl herdr --cluster hpc1 --job <id> read rev --lines 200
orchardctl slurm hpc1 cancel <id>
```

`exec` puts the remote exit code in `rc` and still exits 0, because orchard itself worked. One argument after `--` is a shell string that runs on the target (`$VAR`, `|`, `&&` expand there). Several arguments are quoted word by word.

Every command prints JSON on stdout. On an error, it prints `{"error", "message"}` on stderr and exits with code 1. See `runbooks/` for the standard procedures.

## Layout

```
.
├── src/orchardctl/
│   ├── transport.py   # SSHTransport (system OpenSSH), JobTransport (into a running job via head, job_exec template)
│   ├── inventory.py   # load + check inventory.yaml
│   ├── slurm.py       # SlurmAdapter: submit / queue / job / cancel / wait_running; ownership tag
│   ├── herdr.py       # HerdrClient: server up/down/status, agents, start, prompt, wait, read, keys
│   └── cli.py         # orchardctl entry point (JSON out)
├── tests/             # offline tests with a fake transport
├── runbooks/          # procedures the master agent follows
├── inventory.example.yaml
├── reports/           # YYYY-MM-DD_worklog.md + _summary.md
├── memory/ + MEMORY.md
├── state/             # runtime state (gitignored)
└── CLAUDE.md          # canonical agent instructions (AGENTS.md, .cursorrules point here)
```

## Project Scope

**Goal.** A master agent can bring up, watch, drive and tear down remote coding-agent sessions (herdr) on SSH nodes and Slurm clusters from one local machine, safely and reproducibly.

**Success criteria.**
1. From a clean checkout and a valid inventory, `launch-herdr`, then `herdr start`, then `prompt`, then `read`, then `cancel` works end to end on a real cluster.
2. orchard never cancels or kills a job or process it did not start, unless a person confirms it (`--force`).
3. Each action is one auditable shell command (`-v` logs it).

**Verifier.** `pytest -q` (offline). `runbooks/smoke-test.md` on a real head node (online).

**Scope boundary.**
- In scope: SSH nodes, Slurm through the head node, a Slurm-like in-house scheduler (enter-a-job only, via `job_exec`), herdr CLI control.
- Out of scope for v0.1: other schedulers (PBS, LSF, K8s), a long-running daemon, a web UI, installing herdr on targets, and changing cluster configuration.

**Constraints.**
- Local machine has no Slurm.
- Python ≥ 3.10.
- The only runtime dependency is PyYAML.
- SSH uses the system `ssh`, so `~/.ssh/config` applies as is.
