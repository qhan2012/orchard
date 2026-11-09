---
name: slurm-via-head
description: Slurm is reached only through the head node; ownership tag rule
type: project
---
- The local machine has no Slurm (user statement, 2026-11-09). All Slurm CLI commands run on the head node over SSH.
- To reach a running job without SSH to a compute node, run `srun --jobid=J --overlap` on the head node. This needs Slurm 20.11 or later.
- orchard tags its jobs with `--comment=orchard:<tag>`. cancel acts only on tagged jobs in `squeue --me`.
- Match rows by job id. Never trust the row order. (A smoke-test shim showed that a row-0 assumption cancels the wrong job.)
