# Run a fleet of agents (the attention loop)

Use this when more than one agent runs at the same time, on one or more targets.

Why this shape: the person is the bottleneck, not the agents. The loop below
follows the workflow DHH describes in Lex Fridman Podcast #501 (2026-08-26,
"Programming setup for AI Agents" and "Best AI coding harnesses"):
herdr as "tmux plus agent notifications" on several machines, one model
builds and a different model reviews, a scheduled bot sends a digest, and a
person makes the final call. Source: https://lexfridman.com/dhh-2-transcript

## The loop

1. **Bring up targets.** `slurm <c> launch-herdr --run <codename>` or `herdr --node <n> up --run <codename>`.
   The ledger (`state/ledger.jsonl`) records each target. Use one code name per piece of work.
2. **Plan, then build.** Start one builder per independent task:
   `herdr ... start <name> --kind <builder kind> --cwd <repo> --role builder --run <codename>`.
   For a large task, start a `--role planner` agent first. Give the plan to the builder as its prompt.
   `start` refuses past `fleet.max_agents` live agents (default 16). That is the attention budget. Do not raise it to go faster. Finish or stop an agent first.
3. **Watch, do not poll by hand.** Run `orchardctl watch` in one terminal (or `watch --once` from cron).
   It prints one JSON line when an agent:
   - `needs_decision`: it is `blocked` on an approval or a question. A person must read it and decide. The master agent does not send keys to approve.
   - `finished`: it is `done`. Go to step 4.
   - `unclassified`: herdr cannot classify it. Read it.
   - `agent_gone` or `target_unreachable`: check `slurm status` or the node.
   Each event also runs `fleet.notify` (desktop or phone).
4. **Cross-review every finished builder.** Run `herdr ... review <builder> --base <ref>`.
   This starts a reviewer of a different kind (`fleet.roles.reviewer`) in the builder's cwd, with a read-only review prompt that ends in `VERDICT: ship | fix-first | rework`.
   - `fix-first`: prompt the builder with the findings. Then review again.
   - `rework`: escalate to a person.
   - `ship`: the person merges. orchard and the master agent never merge.
5. **Digest for the person.** Run `orchardctl digest --notify` (by hand, or from cron every 1 to 2 hours).
   It writes `state/digests/<date>.md`: what needs you first, then the screens of those agents. Working agents are not read.
6. **Clean up.** Run `orchardctl cleanup` (dry run). Check the plan. Then run `cleanup --yes [--run <codename>]`.
   It stops only targets that orchard opened (the ledger says `owned`).

## Example cron (local machine)

```cron
*/5 * * * *  cd ~/orchard && orchardctl watch --once >> state/watch.log 2>&1
17 */2 * * * cd ~/orchard && orchardctl digest --notify >> state/digest.log 2>&1
```

`watch` saves its last poll in `state/watch.last.json`, so each cron run reports only what changed since the previous run. Use `watch --fresh` to report every agent that needs you now.

## Rules that still apply

- A timeout is not proof of failure. `read` before you resend.
- `blocked` goes to a person. Never approve on their behalf.
- The reviewer does not edit files. If it does, discard its changes and report it.
