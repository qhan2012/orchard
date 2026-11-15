# README blocks for workers that run locally

Add one of these under Constraints in the workspace `README.md`. Fill every `<...>` from `targets.yaml` and the task file. Leave out the `Job exec` line if the target has no `job_exec`.

## Experiment with `runner: local`

```markdown
### Remote
- Target: <target>
- Enter: <enter>
- Job exec: <job_exec>
- Remote dir: <remote workdir>/<task>
- Rules:
  - Run every build, test, and experiment on the remote, through Enter.
  - Send each remote command as one single-quoted string: <enter> '<command>'.
  - Code and full logs stay on the remote. Do not copy large files to local.
  - Write reports and memory locally only.
  - Do not touch anything outside Remote dir without permission.
```

## Research

```markdown
### Remotes (read-only)
- <target>: <enter> — <absolute path to read>
- <target>: <enter> — <absolute path to read>
- local copy: <orchard>/reports/tasks/<closed task>
- Rules:
  - Read only. Do not run jobs, and do not change or make files on a remote.
  - Send each remote command as one single-quoted string: <enter> '<command>'.
  - Copy only small files (reports, metrics). Do not copy checkpoints or datasets.
  - If the analysis needs a new experiment, write the request in the report. Do not run it.
```
