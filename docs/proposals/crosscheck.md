# Proposal: crosscheck gates

Status: **proposal for the person's review, 2026-11-15. Not agreed. Nothing here is built.**
After approval, this text becomes `DESIGN.md` section 5b and the changes in section 9 below.

## 1. Problem

Today the master looks at a worker only for status: `/check` reads the herdr
state, the worklog tail, and the summary. Nobody checks the **content** of
the worker's work before `done`:

- A worker can misread the plan and work for hours on the wrong goal.
- An experiment can compare unlike things, or cost much more than expected.
- A summary can state a number that the logs do not show.

A crosscheck must find these faults early, when they are cheap.

## 2. Principles

1. **Check evidence, not statements.** The reviewer reads the plan, the
   logs, and the config. It does not accept "done" from the worker.
2. **The master decides. The person decides only the exceptions** (section 7).
   This keeps the earlier decision that the flow does not stop for the person.
3. **A fresh context does the review.** A new skill `/review` runs in a
   subagent (`context: fork`), like `/check`. The reviewer did not write the
   plan, and its output stays out of the master's context. This follows the
   `CLAUDE.md` rule "a check of another agent's work: a fresh context does it".
4. **No code.** Gates are files in the workspace, three lines in the plan,
   and one skill. Like all worker rules, they are instructions. No hook or
   sandbox enforces them (section 10).
5. **Cost follows risk.** Small runs have no gate. A waiting worker does
   useful work.

## 3. The gates

| Gate | When the worker writes it | File in the workspace | Blocks |
|---|---|---|---|
| `plan` | After it reads the plan and does its first research; before any other work | `reports/gates/plan.md` | every experiment that is not a small run |
| `design` | Before each experiment that is not a small run | `reports/gates/design-<code name>.md` | that experiment |
| `result` | At the end: it is the summary | `reports/<date>_summary.md` | the report to the person, and a follow-up (`then:`) |

The `plan` gate holds two checks in one file: **understanding** and
**breakdown**. They are one stop, not two, because a breakdown costs the
worker only minutes, and each stop costs up to one check interval
(section 8). Open question 1 lets you split them.

**Monitoring during a run** is not a gate. `/check` gets two more signals
(section 6).

A **small run** is a smoke test, or a run that the worker expects to cost
less than `small_run` (default 0.5 resource-hours; open question 3). It
needs a worklog entry only. A debug task does many such runs, and a gate for
each would stop the work. A **resource-hour** is a GPU-hour if the run uses
GPUs, otherwise a node-hour.

Which gates a task has, in the new task field `gates:`:

| Task | Default `gates:` |
|---|---|
| `experiment` | `plan, design, result` |
| `research` | `plan, result` (it runs no experiments) |
| adopted (`started_by: person`) | none: the agent is the person's, and its directory can have no harness files |

The person can change it on the launch card ("no gates", "result only").

## 4. What the worker writes

The master adds a `### Gates` block to the plan Constraints (text kept in
`.claude/skills/publish/blocks.md`). The harness itself does not change.

**`plan.md`**
1. The plan in the worker's own words: goal, success criteria, verifier,
   scope boundary, constraints.
2. What it will not do.
3. Questions, each with the default answer that it will use.
4. The task list. Each task has: what is done when, what it depends on, and
   which success criterion it serves.

**`design-<code name>.md`** (the code name is the harness `experiments/<codename>`)
1. The question that this experiment answers, and its success criterion.
2. The variable under test, and what stays the same: data, hardware, config, seed.
3. The baseline, and the file where its number comes from.
4. The metric and how it is computed.
5. The correctness check, and whether it is a different run from the perf run.
6. The cost: resource-hours and wall time. A sweep is one design; give the total.
7. The first sign that the run works, and when to expect it.
8. The conditions that make the worker stop the run.
9. The exact command, the config path, and the code commit.

**Summary (`result` gate).** One more rule: for each result number, the
summary gives the file and the command that show it.

**Rules for the worker at a gate**
- While a verdict is missing, go on with research, setup, and small runs. Do
  not start a gated experiment.
- The verdict of a gate is a file in `reports/gates/`: `plan.verdict.md`,
  `design-<code name>.verdict.md`, `summary.verdict.md`. Look for it before
  each launch, and when nothing else is left to do. The master also sends a prompt when the worker is idle.
- `pass`: go on. `revise`: change the gate file, then wait again.
  `escalate`: stop; the person decides.
- The harness rule "decide after 30 min" does not apply to a gate.

## 5. The review: `/review <task> [<gate>]`

It runs in a subagent. Like `/check`, it **looks, decides, records, and
reports**. It does not prompt, start, or stop an agent, and it changes
nothing on a target except the verdict file.

1. Read the plan: `README.md § Project Scope` in the workspace (the source
   of truth), and `tasks/<task>.md`.
2. Read the gate file. Check each item of the list for that gate:

   | Gate | Checklist |
   |---|---|
   | `plan`: understanding | Each of the five plan items is there and means the same as the plan. Nothing is added to the scope, nothing is dropped. Each default answer agrees with the plan. |
   | `plan`: breakdown | Each success criterion has a task. Each task has a done condition. A smoke test comes before the first long run. The order respects the dependencies. |
   | `design` | Only one variable changes (harness rule 4). The baseline number exists in the named file. The metric measures the success criterion. Correctness and perf are separate runs (rule 6). No hardcoded seed or parameter (rule 7). The cost is inside the limit (section 7). The stop conditions can be seen in a log. The config file and commit exist. |
   | `result` | Each number in the summary is in the named log (the reviewer runs the named command). The config and commit that ran are those of the passed design. Each success criterion is answered, with yes or no. The correctness run exists. No scheduler job named `<task>-*` still runs. |

3. Write the verdict file in the workspace `reports/gates/` (names in
   section 4), and add one line to `tasks/<task>/gates.md` (the master's record):

   ```markdown
   # Verdict: design-lr-sweep, round 1
   verdict: revise            # pass | revise | escalate
   reviewed: 2026-11-15T14:02
   ## Checklist
   - [pass] one variable — evidence: design-lr-sweep.md:12, config diff has 1 line
   - [fail] baseline — experiments/base/metrics.json has no `val_loss`; name the right file
   - [not checked] commit — codebases/ not readable from here: <error>
   ## Required changes
   1. ...
   ```

   **Each item needs evidence**: a file and line, or a command and its
   output line. An item without evidence is `not checked`. A verdict is
   `pass` only if no item is `fail` or `not checked`. This is the guard
   against a reviewer that agrees with everything.
4. Return at most 8 lines to the master: task, gate, round, verdict, and the
   failed items.

The reviewer reads. It does not run the experiment again.

**The master acts on the report:**

| Verdict | Master does |
|---|---|
| `pass` | If the worker is idle: prompt "Read reports/gates/<verdict file> and continue." If it works: nothing; the worker finds the file. |
| `revise` | The same prompt. A gate can get two `revise` verdicts. If the third review still fails, its verdict is `escalate`. |
| `escalate` | Tell the person the failed items. Stop the `/loop` only if the worker is idle. Do not prompt the worker. |
| `result` gate `pass` | Report `done` to the person, with the verdict. Publish a follow-up (`then:`) only now. |
| `result` gate not `pass` | Do not report `done`. A failed `result` gate is one more stop condition for a follow-up. |

## 6. How a gate is found, and monitoring during a run

`/check` already reads the workspace. It gets three more lines:

- **Gate waiting**: a file in `reports/gates/` (or the summary) has no
  verdict file, or is newer than its verdict file. The report gets the line
  `gate: <name> waiting`. The task `status` does not change, because the
  worker can still work. The master then runs `/review`.
- **Launch without a pass**: a directory `experiments/<code name>/` is newer
  than the last check and has no passed `design-<code name>` verdict, and it
  is not marked as a small run in the worklog. The report says so. The master
  tells the person. It does not stop the run (ownership rule).
- **No progress**: a passed design gives the time of the first sign of
  life. If the worklog has no new entry long after that time, the report
  says so.

The gate state is in files in the workspace, so it survives a restart of the
master, a restart of the worker after a kill, and `/fallback` (which must
copy `reports/gates/` with the worklog).

## 7. When the person decides

The master decides every gate, except these cases. Then the gate is
`escalate` and the master waits for the person.

| Case | Wait |
|---|---|
| The design costs more than `ask_above` (default 8 resource-hours; open question 2) | Until the person answers. **No 30-minute default**: a wrong run costs more than the wait. |
| A gate fails after two `revise` rounds | Until the person answers |
| The reviewer finds that the plan contradicts itself, or a question has no answer in the plan | 30 minutes, then the worker's default answer (`DECISION:` in the worklog) |
| The result is the opposite of what the plan expects, or a success criterion is "no" | The master reports `done` with this on the first line. No follow-up starts by itself. |
| An item is `not checked` and the reviewer cannot get the evidence | Until the person answers |

`ask_above` and `small_run` are site values. They go in the `local` entry of
`targets.yaml`, and the launch card shows them (`Gates:` line), so the person
can change them for one task at the one review screen.

## 8. Cost

- **Time.** A gate is found by a check, so a waiting gate costs up to one
  check interval, plus some minutes for the review. **A task with gates
  needs a check cadence** (the same rule as a task with `then:`). With no
  cadence, the master says so at the review screen.
- **Worker time lost**: little. The worker does setup and small runs while it waits.
- **Tokens.** One subagent run per gate and round. A typical experiment
  task: 1 plan review, 1 to 3 design reviews, 1 result review.

## 9. Changes if approved

| File | Change |
|---|---|
| `.claude/skills/review/SKILL.md` (new) | the procedure of section 5, with the checklists |
| `.claude/skills/publish/` | launch card `Gates:` line; step 5 adds the `### Gates` block from `blocks.md` |
| `.claude/skills/check/SKILL.md` | the three lines of section 6 |
| `.claude/skills/fallback/SKILL.md` | copy `reports/gates/` too |
| `CLAUDE.md` "After a check" | act on `gate:` lines; `done` is reported only after the `result` gate |
| `tasks/TEMPLATE.md` | field `gates:` |
| `targets.example.yaml` | `ask_above`, `small_run` in `local` |
| `DESIGN.md` | new section 5b; section 9 keeps "cross-model review" out of scope |
| `README.md`, `docs/first-run.md` | seven skills; one first-run step for a gate |

Each row is one small PR, in this order: `/review` and the block text
first, then `/check`, then the rest.

## 10. Known limits

- **Instructions only.** A worker can ignore a gate. "Launch without a pass"
  finds this after the launch, at the next check.
- **Same model.** The reviewer has a fresh context but the same model as
  the worker by default, so they can share a blind spot. A reviewer with
  another model stays out of scope (`DESIGN.md` 9).
- **The reviewer checks what is recorded.** A number that the worker never
  logged cannot be checked. The result is `not checked`, then `escalate`.
- **No rerun.** The reviewer confirms that the logs show the number. It does
  not confirm that a second run gives the same number.
- **Delay.** Each gate waits for a check (section 8).
- **The prompt after a verdict** is sent only to an idle worker. If herdr
  0.8.2 queues a prompt for a working agent is not verified, so the design
  does not need it.
- **Not run on a real machine**, like the rest of this repo.

## 11. Open questions for the review

| # | Question | Recommended default |
|---|---|---|
| 1 | `plan` gate: understanding and breakdown in one stop, or two? | One stop |
| 2 | `ask_above`: above which cost does the person decide a design? | 8 resource-hours. **This number is a guess; set it.** |
| 3 | `small_run`: below which cost does a run need no gate? | 0.5 resource-hours, and every smoke test |
| 4 | Above `ask_above`, wait for the person with no time limit? | Yes |
| 5 | `revise` rounds before the person decides | 2 |
| 6 | Does a `research` task need the `plan` gate, or only `result`? | Both |
| 7 | Can the reviewer write the verdict file into the workspace, or must the master do it? | The reviewer: the text stays out of the master's context |
| 8 | Gates on by default for each new task, or only when the person asks? | On by default for `experiment` and `research`; shown on the launch card |
