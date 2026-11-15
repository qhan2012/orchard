---
task:                # unique; matches [a-z][a-z0-9_-]{0,31}; also the workspace directory and herdr agent name
kind: experiment     # experiment (works on one target) | research (local, reads targets, web search)
target:              # an entry of targets.yaml; `local` (this machine) for a research task or an adopted local agent
runner:              # herdr | local (default: the target's runner)
agent: claude        # agent kind (herdr --kind): the person's choice, else the entry's `agent` in targets.yaml, else claude
started_by: orchard  # orchard | person (adopted with /adopt)
session:             # herdr session of the agent: `orchard` on a target; locally the master's own session (usually `default`)
agent_name:          # herdr agent target; default: the task name
agent_session:       # native agent session id, written by /close if herdr reports one
workspace:           # <target>:<absolute path>  or  local:<absolute path>; the path ends in myworks/<task>
remote_dir:          # experiment with runner: local only
remotes:             # research only: list of "<target>:<absolute path>" to read
from:                # the research task whose `## Proposed task` this task uses; empty = none
then:                # research only: follow-up experiment approved in advance (target, agent, args, directory, limits); cleared when it starts
files:               # input files, moved from files/ to tasks/<task>/ at publish and copied to the workspace files/
harness:             # full harness commit sha used (from HARNESS at publish time)
status: planned      # planned | running | blocked | idle | killed | done | closed
kills: 0
unreachable: 0       # checks in a row that could not reach the target; written by /check
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
