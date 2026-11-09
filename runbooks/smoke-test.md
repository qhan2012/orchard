# Smoke test (online, real cluster)

Run this before you rely on orchard for a long run, and after you change `src/`. Record each step's output (job id, state) in the worklog.

| # | Step | Command | Pass if |
|---|---|---|---|
| 0 | SSH works without a prompt | `ssh -o BatchMode=yes <head> true` | exit 0 |
| 1 | Inventory parses | `orchardctl inventory` | your clusters and nodes are listed |
| 2 | Slurm reachable | `orchardctl slurm <c> queue` | JSON list (can be empty) |
| 3 | herdr exists on compute | `orchardctl slurm <c> submit` a script that runs `herdr --version`, then `status` | job COMPLETED. The output file shows a version |
| 4 | Launch herdr in a job | `orchardctl slurm <c> launch-herdr --opt time=00:20:00 --wait 600` | `job.state == RUNNING` |
| 5 | Reach it with srun | `orchardctl herdr --cluster <c> --job <id> status` | server status JSON |
| 6 | Start an agent | `orchardctl herdr --cluster <c> --job <id> start smoke --kind claude --cwd '~'` | `pane_id` returned |
| 7 | Prompt and read | `prompt smoke "Reply with the word ready." --timeout-ms 120000`, then `read smoke` | the text contains `ready` |
| 8 | Guard works | `orchardctl slurm <c> cancel <id of a job you own without the tag>` | `OwnershipError`, and the job is still running |
| 9 | Clean up | `orchardctl slurm <c> cancel <id>` | the job leaves `squeue --me` |

Known requirements to check on a new cluster:
- `srun --overlap` needs Slurm 20.11 or later.
- `squeue --me` needs Slurm 20.02 or later.
- The `Comment` column in `sacct` is empty unless the cluster sets `AccountingStoreFlags=job_comment`. Live ownership checks use `squeue`, so they still work.
- The agent CLI (for example `claude`) must be installed and logged in on the compute node.
