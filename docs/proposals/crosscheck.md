# Proposal: crosscheck gates

Status: **proposal for the person's review, 2026-11-15; two-level check and metrics added 2026-11-16. Not agreed. Nothing here is built.**
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

## 2a. Two levels of check

| | Light check: `/check` | Deep check: `/review` |
|---|---|---|
| When | On a cadence (`/loop 30m /check`), and when the person asks | On an event: a gate file waits, or a light check reports a problem. Also when the person asks ("deep check <task>"). Never on a clock |
| Reads | herdr state, the worklog tail, the summary, gate and verdict file names, the metrics tail, the watch list | the plan, the gate file, and the evidence that it names: logs, configs, commits. It runs the commands that the gate names |
| Output | status, latest progress, **latest metrics**, signals (section 6) | a verdict with evidence for each item (section 5) |
| Cost | a few commands; a short report | one subagent that reads many files |

Both run in a subagent, so neither fills the master's context.

The light check finds; the deep check judges. The light check never
decides if a number is right. It only compares it with the watch list that a
deep check wrote (section 6). A deep check on a clock would read the same
files again and again with nothing new to judge, so it runs only on an event.

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

**Monitoring during a run** is not a gate. The light check reports the
metrics and the signals of section 6 on each run.

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
4. The metric, how it is computed, and its name in `reports/metrics.log`.
5. The correctness check, and whether it is a different run from the perf run.
6. The cost: resource-hours and wall time. A sweep is one design; give the total.
7. The first sign that the run works, and when to expect it.
8. The conditions that make the worker stop the run.
9. The exact command, the config path, and the code commit.
10. The watch list: for each metric in `reports/metrics.log`, its normal
    range, and by which step or time. The reviewer copies it into the verdict
    (section 5) for the light check.

**`reports/metrics.log`** (every `experiment` task, with or without gates).
The worker appends one line each time a run reports a metric. It never
edits old lines.

```
2026-11-15T14:20  lr-sweep  step=4000  val_loss=2.31  tok_per_s=5120
2026-11-15T14:50  lr-sweep  step=6000  val_loss=nan   tok_per_s=5090
```

Fields are separated by two or more spaces: time, code name, then
`name=value` pairs. A run with no metric yet writes nothing. The worker
writes this file in addition to its own logs; the logs stay the evidence.

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
   ## Watch               # design gate with verdict pass only; the light check reads this section
   - lr-sweep val_loss: finite, < 3.0 by step 2000
   - lr-sweep tok_per_s: > 4500
   - lr-sweep metrics.log: a new line every 30 min or less
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

## 6. The light check: metrics, gates, and monitoring during a run

`/check` already reads the workspace. It gets these additions. All are
reads of small files; it runs no evaluation and opens no full log.

- **Metrics, in every report.** `tail -n 40 W/reports/metrics.log`. For each
  code name that has a line since the last check, report the newest value of
  each metric, its step, and its age. Write the same to a new task-file
  field, `metrics:` (one line), so the last values survive a restart.
  If a task has a running experiment and `metrics.log` has no new line, say
  so.
- **Metric out of watch.** Compare each newest value with the `## Watch`
  lines in the passed design verdicts. The comparison is plain: a range, a
  bound, `finite`, or "a new line every N minutes". A value outside it gives
  the line `watch: <code name> <metric>=<value>, expected <rule>`. The light
  check does not explain it; the master runs `/review` (section 6a).

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

The report for each task grows from 8 to at most 12 lines:

```
lr-sweep-debug | running | was running | box1
latest: iteration 4, sweep 3 of 5 running
metrics: lr-sweep step=6000 val_loss=nan tok_per_s=5090 (10 min ago)
watch: lr-sweep val_loss=nan, expected finite, < 3.0 by step 2000
gate: design-lr-sweep-2 waiting
```

### 6a. What the master does with the light report

| Line | Master does |
|---|---|
| `metrics:` | Gives it to the person as part of the report. Nothing else. |
| `watch:` (out of watch) | Tells the person, and runs `/review <task>` on that experiment. The review checks the logs and gives `pass` (a false alarm; it can change the watch list), `revise` (the worker must fix and say so), or `escalate`. The master does not stop the run (ownership rule); the worker stops it if its own stop condition is true. |
| no new metrics while a run is running | Same as "no progress": tell the person. |
| `gate: ... waiting` | Runs `/review`. |
| launch without a pass | Tells the person. |

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
| `.claude/skills/publish/` | launch card `Gates:` line; step 5 adds the `### Gates` block from `blocks.md`, and for every `experiment` the standard constraint "Append each metric to `reports/metrics.log` (format in the block)" |
| `.claude/skills/check/SKILL.md` | the additions of section 6: metrics, watch, gate, launch, progress; report of up to 12 lines |
| `.claude/skills/fallback/SKILL.md` | copy `reports/gates/` too |
| `CLAUDE.md` "After a check" | the table of section 6a; `done` is reported only after the `result` gate |
| `tasks/TEMPLATE.md` | fields `gates:` and `metrics:` |
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
- **Metrics are what the worker writes.** The light check trusts
  `metrics.log`. A wrong line there is found only by a deep check, which
  reads the logs: at the `result` gate, or after a `watch:` line.
- **The watch list is only as good as the design.** A failure that no watch
  line covers is seen only as "no progress" or at the `result` gate.
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
| 9 | Metrics file: one `reports/metrics.log` per workspace, in the format of section 4? | Yes. Another format (CSV, JSON lines) is fine if it is one line per reading |
| 10 | On a `watch:` line, does the master also run `/review` at once, or only tell the person? | Both: tell the person, and run `/review` |
