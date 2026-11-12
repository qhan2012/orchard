---
task:                # short, unique, kebab-case; also the workspace directory name
target:              # a name from targets.yaml
runner:              # herdr | local (default: the target's runner)
agent: claude        # agent kind
started_by: orchard  # orchard | person (adopted with /adopt)
session: orchard     # herdr session; `default` is the default session
agent_name:          # herdr agent target; default: the task name
workspace:           # <target>:~/myworks/<task>  or  local:~/myworks/<task>
remote_dir:          # runner: local only
harness:             # full harness commit sha used (from HARNESS at publish time)
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
