---
task:                # short, unique, kebab-case; also the workspace directory name
target:              # a name from targets.yaml
runner:              # herdr | local (default: the target's runner)
agent: claude        # agent kind to start
workspace:           # <target>:~/myworks/<task>  or  local:~/myworks/<task>
remote_dir:          # runner: local only
harness:             # harness commit used for the workspace
status: planned      # planned | running | blocked | idle | killed | done
kills: 0
check:               # set at runtime, for example "every 10m"; empty = only when asked
last_checked:
latest:
---

## Plan (draft; after publish the workspace README.md is the source of truth)

- **Goal.**
- **Success criteria.**
- **Verifier.**
- **Scope boundary.**
- **Constraints.**
