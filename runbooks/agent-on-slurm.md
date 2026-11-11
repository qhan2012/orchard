# Run a coding agent on a Slurm compute node

1. **Request resources.**
   Run `orchardctl slurm <c> launch-herdr --opt time=HH:MM:SS [--opt gres=gpu:1] --wait 900`.
   Record the `job_id` and `tag`.
   The job keeps one headless herdr server alive (`exec herdr --session <s> server`). When the job ends, the server and all its agents end too.
2. **Start the agent.**
   Run `orchardctl herdr --cluster <c> --job <id> start <name> --kind <kind> --cwd <abs or ~ path>`.
   The name must match `[a-z][a-z0-9_-]{0,31}` and must be unique in the session.
3. **Drive the agent.**
   Run `prompt <name> "<task>" --timeout-ms N`. This waits for the first settled state: `idle`, `done`, or `blocked`.
   - `idle` or `done`: run `read <name> --lines 200`, then check the result.
   - `blocked`: run `read`, then escalate to a person. Do not approve on their behalf.
   - `timeout` or `agent_prompt_stalled`: run `read` first. Resend only if the prompt is not on screen.
4. **Watch.**
   Run `orchardctl slurm <c> status <id>` and `herdr ... agents`.
   If the job leaves the RUNNING state, the agents are gone. Look at the job's output file on the head node.
5. **Finish.**
   Copy the results you need, then run `orchardctl slurm <c> cancel <id>`.
   Log the job id, the time it ran, and the result in the worklog.

## Plain SSH node (no scheduler)

Run `orchardctl herdr --node <n> up` to start a detached server (the log goes to `~/.orchard/`). Then do the same steps as above with `--node <n>`. When you finish, run `herdr --node <n> down`. `down` works only on a server that orchard started.

## A herdr session that a person started

1. The person starts herdr on the target with the session name from the inventory (`herdr --session <s>`), or tells you the name they used.
2. Register it: `orchardctl session adopt --node <n>` or `--cluster <c> --job <id>`. Add `--session <name>` if the name differs, and `--note` to say what it is.
3. Watch and prompt as usual (`agents`, `read`, `prompt`). Only one side drives an agent at a time: confirm with the person before you send a prompt.
4. Do not stop the server and do not cancel the job. The person does that.
