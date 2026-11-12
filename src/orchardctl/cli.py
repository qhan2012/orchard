"""orchardctl: the command surface the master agent (or a human) uses.

All output is JSON on stdout so an agent can parse it. Errors print
{"error": ...} on stderr and exit 1. ``watch`` is the one streaming command:
it prints one JSON event per line.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from . import fleet as fl
from . import inventory as inv_mod
from .herdr import HerdrClient
from .ledger import Ledger, default_path, job_key, node_key
from .slurm import SlurmAdapter, check_job_id, herdr_job_script
from .transport import SrunTransport

NODE_PROBE = (
    "echo host=$(hostname); echo user=$(whoami); "
    "echo load=\"$(cut -d' ' -f1-3 /proc/loadavg)\"; echo cpus=$(nproc); "
    "echo mem_mb=$(free -m | awk '/^Mem:/{print $2\"/\"$7\" total/avail\"}'); "
    "(command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total "
    "--format=csv,noheader | sed 's/^/gpu=/') || echo gpu=none; "
    "echo herdr=$(command -v herdr || echo missing)"
)

STREAMED = object()  # run() already wrote its output


class BudgetError(RuntimeError):
    pass


class OwnershipError(RuntimeError):
    pass


def _kv(lines: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for line in lines.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out.setdefault(k, []).append(v)
    return {k: v[0] if len(v) == 1 else v for k, v in out.items()}


def _opts(pairs: list[str] | None) -> dict[str, str]:
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--opt expects key=value, got {p!r}")
        k, v = p.split("=", 1)
        out[k] = v
    return out


class Ctx:
    """Inventory + ledger + a way to reach herdr on any target."""

    def __init__(self, inv: inv_mod.Inventory, ledger: Ledger):
        self.inv = inv
        self.ledger = ledger

    def client(self, t: fl.Target, session: str | None = None) -> HerdrClient:
        if t.kind == "node":
            tr = self.inv.node(t.node).transport()
        else:
            tr = SrunTransport(self.inv.cluster(t.cluster).transport(), check_job_id(t.job))
        return HerdrClient(tr, session=session or self.inv.herdr_session, binary=self.inv.herdr_binary)

    def fleet_targets(self, extra: list[str] | None = None, all_nodes: bool = False
                      ) -> list[tuple[fl.Target, str | None]]:
        """Open ledger targets, plus --target specs, plus (optionally) every inventory node."""
        seen: dict[str, tuple[fl.Target, str | None]] = {}
        for rec in self.ledger.open_targets():
            seen[rec.key] = (fl.Target.parse(rec.key), rec.session or None)
        for spec in extra or []:
            t = fl.Target.parse(spec)
            seen.setdefault(t.key, (t, None))
        if all_nodes:
            for name in self.inv.nodes:
                t = fl.Target("node", node=name)
                seen.setdefault(t.key, (t, None))
        return list(seen.values())

    def meta(self, key: str, name: str) -> dict[str, Any] | None:
        return self.ledger.agent(key, name)

    def snapshot(self, extra=None, all_nodes=False) -> dict[str, Any]:
        return fl.snapshot(self.fleet_targets(extra, all_nodes), self.client, self.meta)


def _target(a: argparse.Namespace) -> fl.Target:
    if a.node:
        return fl.Target("node", node=a.node)
    if a.cluster and a.job:
        return fl.Target("job", cluster=a.cluster, job=check_job_id(a.job))
    raise SystemExit("herdr target: give --node NAME, or --cluster NAME --job ID")


def _check_budget(ctx: Ctx, t: fl.Target, adding: int = 1) -> dict[str, Any]:
    """Refuse a new agent once the person's attention budget is spent."""
    snap = ctx.snapshot(extra=[t.key])
    live = snap["live_agents"]
    # A target we cannot reach still holds the agents the ledger says we started there.
    for s in snap["targets"]:
        if not s["ok"]:
            rec = ctx.ledger.targets().get(s["target"])
            live += len(rec.agents) if rec else 0
    limit = ctx.inv.fleet.max_agents
    if live + adding > limit:
        raise BudgetError(
            f"{live} live agents, budget is {limit} (fleet.max_agents). Finish, review, or stop an agent "
            "first (`orchardctl fleet`), or pass --over-budget if a person approved it."
        )
    return {"live_agents": live, "budget": limit}


def run(a: argparse.Namespace) -> Any:
    inv = inv_mod.load(inv_mod.resolve_path(a.inventory))
    ledger = Ledger(Path(a.state).expanduser() / "ledger.jsonl" if a.state else default_path(inv.path))
    ctx = Ctx(inv, ledger)

    if a.cmd == "inventory":
        return {
            "path": str(inv.path),
            "ledger": str(ledger.path),
            "clusters": {k: v.__dict__ for k, v in inv.clusters.items()},
            "nodes": {k: v.__dict__ for k, v in inv.nodes.items()},
            "herdr": {"session": inv.herdr_session, "binary": inv.herdr_binary},
            "fleet": inv.fleet.__dict__,
        }

    if a.cmd == "node":
        r = inv.node(a.name).transport().run(NODE_PROBE, timeout=a.timeout)
        return {"node": a.name, "reachable": r.ok, **(_kv(r.stdout) if r.ok else {"stderr": r.stderr.strip()})}

    if a.cmd == "slurm":
        return _slurm(ctx, a)
    if a.cmd == "herdr":
        return _herdr_cmd(ctx, a)
    if a.cmd == "fleet":
        return ctx.snapshot(a.target, a.all_nodes)
    if a.cmd == "watch":
        return _watch(ctx, a)
    if a.cmd == "digest":
        return _digest(ctx, a)
    if a.cmd == "cleanup":
        return _cleanup(ctx, a)
    if a.cmd == "ledger":
        return {k: v.to_dict() for k, v in ledger.targets().items() if a.all or v.open}

    raise SystemExit(f"unhandled command {a.cmd}")


def _slurm(ctx: Ctx, a: argparse.Namespace) -> Any:
    c = ctx.inv.cluster(a.cluster)
    s = SlurmAdapter(c.transport(), c.sbatch_defaults)
    if a.action == "queue":
        return [j.to_dict() for j in s.queue()]
    if a.action == "status":
        j = s.job(a.job)
        return j.to_dict() if j else {"job_id": a.job, "state": "NOT_FOUND"}
    if a.action == "cancel":
        job = s.cancel(a.job, force=a.force)
        key = job_key(c.name, a.job)
        if key in ctx.ledger.targets():
            ctx.ledger.record("job_cancelled", key)
        return {"cancelled": job.to_dict()}
    if a.action == "submit":
        tag = a.tag or uuid.uuid4().hex[:8]
        job_id = s.submit(Path(a.script).read_text(), tag, **_opts(a.opt))
        return {"job_id": job_id, "tag": tag, "cluster": c.name}
    if a.action == "launch-herdr":
        session = a.session or ctx.inv.herdr_session
        tag = a.tag or f"herdr-{uuid.uuid4().hex[:8]}"
        opts = {"job-name": f"orchard-{session}", **_opts(a.opt)}
        job_id = s.submit(herdr_job_script(session, ctx.inv.herdr_binary), tag, **opts)
        ctx.ledger.record("job_launched", job_key(c.name, job_id), session=session, tag=tag, run=a.run)
        out: dict[str, Any] = {"job_id": job_id, "tag": tag, "session": session,
                               "target": job_key(c.name, job_id)}
        if a.wait:
            out["job"] = s.wait_running(job_id, timeout=a.wait).to_dict()
        return out
    raise SystemExit(f"unhandled slurm action {a.action}")


def _herdr_cmd(ctx: Ctx, a: argparse.Namespace) -> Any:
    t = _target(a)
    h = ctx.client(t, a.session)
    act = a.action
    if act == "version":
        return {"version": h.version()}
    if act == "status":
        return h.server_status()
    if act == "up":
        if t.kind != "node":
            raise SystemExit("herdr up is for plain nodes; on Slurm use `slurm <c> launch-herdr`")
        log = h.start_server()
        ctx.ledger.record("server_up", t.key, session=h.session, run=a.run)
        return {"log": log, "target": t.key}
    if act == "down":
        if not ctx.ledger.started(t.key) and not a.force:
            raise OwnershipError(
                f"orchard did not start the herdr server on {t.key} (not in {ctx.ledger.path}). "
                "Use --force only after a person confirms it is safe to stop."
            )
        out = h.stop_server()
        ctx.ledger.record("server_down", t.key)
        return out
    if act == "agents":
        return h.agents()
    if act == "get":
        return h.agent(a.target)
    if act == "read":
        return {"target": a.target, "text": h.read(a.target, lines=a.lines, source=a.source)}
    if act == "prompt":
        return h.prompt(a.target, a.text, wait=not a.no_wait, timeout_ms=a.timeout_ms)
    if act == "wait":
        return h.wait(a.target, until=a.until, timeout_ms=a.timeout_ms)
    if act == "start":
        budget = None if a.over_budget else _check_budget(ctx, t)
        out = h.start_agent(a.name, a.kind, a.cwd, agent_args=a.agent_args)
        ctx.ledger.record("agent_started", t.key, session=h.session, name=a.name, kind=a.kind,
                          role=a.role, cwd=a.cwd, run=a.run)
        return {**out, "target": t.key, "budget": budget}
    if act == "review":
        return _review(ctx, t, h, a)
    if act == "keys":
        return h.send_keys(a.target, *a.keys)
    raise SystemExit(f"unhandled herdr action {act}")


def _review(ctx: Ctx, t: fl.Target, h: HerdrClient, a: argparse.Namespace) -> Any:
    """Maker/checker: a different model reviews the builder's work in the same directory."""
    info = h.agent(a.builder)
    agent = (info.get("result") or {}).get("agent", info) if isinstance(info, dict) else {}
    cwd = a.cwd or agent.get("cwd") or agent.get("foreground_cwd")
    if not cwd:
        raise RuntimeError(f"cannot find the cwd of agent {a.builder!r}; pass --cwd")
    builder_kind = agent.get("agent") or (ctx.ledger.agent(t.key, a.builder) or {}).get("kind")
    kind = a.kind or ctx.inv.fleet.roles.get("reviewer", "codex")
    if builder_kind and kind == builder_kind and not a.same_kind:
        raise ValueError(
            f"reviewer kind {kind!r} is the same as the builder's. A different model catches different "
            "mistakes. Pick another --kind, or pass --same-kind on purpose."
        )
    name = a.name or fl.reviewer_name(a.builder)
    budget = None if a.over_budget else _check_budget(ctx, t)
    started = h.start_agent(name, kind, cwd)
    ctx.ledger.record("agent_started", t.key, session=h.session, name=name, kind=kind, role="reviewer",
                      cwd=cwd, run=a.run, of=a.builder)
    prompt = fl.review_prompt(a.builder, builder_kind, a.base, a.focus)
    res = h.prompt(name, prompt, wait=not a.no_wait, timeout_ms=a.timeout_ms)
    return {"reviewer": name, "kind": kind, "builder": a.builder, "builder_kind": builder_kind, "cwd": cwd,
            "target": t.key, "pane_id": started["pane_id"], "budget": budget, "prompt": res,
            "next": f"orchardctl herdr ... read {name} --lines 200"}


def _watch(ctx: Ctx, a: argparse.Namespace) -> Any:
    events_log = ctx.ledger.path.parent / "events.jsonl"
    last = ctx.ledger.path.parent / "watch.last.json"  # lets `watch --once` from cron report only changes
    prev = None
    if last.is_file() and not a.fresh:
        try:
            prev = json.loads(last.read_text())
        except json.JSONDecodeError:
            prev = None
    polls = 0
    while True:
        snap = ctx.snapshot(a.target, a.all_nodes)
        for ev in fl.diff(prev, snap):
            ev = {"ts": snap["ts"], **ev}
            if not a.no_notify:
                ev.update(fl.notify(ctx.inv.fleet.notify, ev) or {})
            line = json.dumps(ev, sort_keys=True)
            print(line, flush=True)
            events_log.parent.mkdir(parents=True, exist_ok=True)
            with events_log.open("a") as f:
                f.write(line + "\n")
        prev = snap
        last.parent.mkdir(parents=True, exist_ok=True)
        last.write_text(json.dumps(snap))
        polls += 1
        if a.once or (a.max_polls and polls >= a.max_polls):
            return STREAMED
        time.sleep(a.interval)


def _digest(ctx: Ctx, a: argparse.Namespace) -> Any:
    targets = ctx.fleet_targets(a.target, a.all_nodes)
    sessions = {t.key: s for t, s in targets}
    snap = fl.snapshot(targets, ctx.client, ctx.meta)
    tails: dict[tuple[str, str], str] = {}
    for r in snap["agents"]:
        if not r["needs_you"] or not r["name"]:
            continue
        try:
            c = ctx.client(fl.Target.parse(r["target"]), sessions.get(r["target"]))
            tails[(r["target"], r["name"])] = c.read(r["name"], lines=a.lines)
        except Exception as e:
            tails[(r["target"], r["name"])] = f"(read failed: {type(e).__name__}: {e})"
    md = fl.render_digest(snap, tails)
    out = Path(a.out).expanduser() if a.out else (
        ctx.ledger.path.parent / "digests" / time.strftime("%Y-%m-%d_%H%M.md"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    result = {"path": str(out), "needs_you": snap["needs_you"], "live_agents": snap["live_agents"],
              "counts": snap["counts"], "unreachable": [t["target"] for t in snap["targets"] if not t["ok"]]}
    if a.notify and snap["needs_you"]:
        result["notify"] = fl.notify(ctx.inv.fleet.notify, {
            "event": "digest", "target": f"{snap['needs_you']} need you", "name": str(out)})
    return result


def _cleanup(ctx: Ctx, a: argparse.Namespace) -> Any:
    """Tear down what orchard started (owned, open ledger targets). Dry run unless --yes."""
    plan = []
    for rec in ctx.ledger.open_targets():
        if a.run and rec.run != a.run and not any(x.get("run") == a.run for x in rec.agents.values()):
            continue
        t = fl.Target.parse(rec.key)
        step: dict[str, Any] = {"target": rec.key, "run": rec.run, "agents": sorted(rec.agents)}
        try:
            if not rec.owned:
                # orchard only started agents on someone else's server: never stop it, just stop tracking.
                step["action"] = "forget (server not started by orchard; remote untouched)"
                if a.yes:
                    ctx.ledger.record("target_gone", rec.key, reason="cleanup of a target orchard does not own")
            elif t.kind == "job":
                s = SlurmAdapter(ctx.inv.cluster(t.cluster).transport())
                job = s.job(t.job)
                if job is None or not job.active:
                    step["action"] = "forget (job already ended)"
                    if a.yes:
                        ctx.ledger.record("target_gone", rec.key, state=job.state if job else "NOT_FOUND")
                else:
                    step["action"] = "scancel"
                    if a.yes:
                        s.cancel(t.job)  # still checks the orchard: tag in squeue --me
                        ctx.ledger.record("job_cancelled", rec.key)
            else:
                step["action"] = "herdr server stop"
                if a.yes:
                    ctx.client(t, rec.session or None).stop_server()
                    ctx.ledger.record("server_down", rec.key)
            step["done"] = bool(a.yes)
        except Exception as e:
            step["error"] = f"{type(e).__name__}: {e}"[:300]
        plan.append(step)
    return {"dry_run": not a.yes, "steps": plan}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="orchardctl", description=__doc__)
    p.add_argument("--inventory", help="inventory file (default $ORCHARD_INVENTORY or ./inventory.yaml)")
    p.add_argument("--state", help="state dir for the ledger (default $ORCHARD_STATE or <inventory dir>/state)")
    p.add_argument("-v", "--verbose", action="store_true", help="log every remote command to stderr")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("inventory", help="show the parsed inventory")

    n = sub.add_parser("node", help="probe an SSH node (load, mem, GPU, herdr)")
    n.add_argument("name")
    n.add_argument("--timeout", type=float, default=30)

    s = sub.add_parser("slurm", help="Slurm on a cluster head, over SSH")
    s.add_argument("cluster")
    ss = s.add_subparsers(dest="action", required=True)
    ss.add_parser("queue", help="your live jobs (squeue --me)")
    st = ss.add_parser("status"); st.add_argument("job")
    ca = ss.add_parser("cancel", help="cancel an orchard-tagged job")
    ca.add_argument("job"); ca.add_argument("--force", action="store_true",
                                            help="also cancel untagged jobs you own")
    su = ss.add_parser("submit", help="sbatch a local script on the head")
    su.add_argument("script"); su.add_argument("--tag")
    su.add_argument("--opt", action="append", metavar="KEY=VALUE", help="sbatch option, repeatable")
    lh = ss.add_parser("launch-herdr", help="start a herdr server inside a Slurm job")
    lh.add_argument("--session"); lh.add_argument("--tag"); lh.add_argument("--run", help="run code name")
    lh.add_argument("--opt", action="append", metavar="KEY=VALUE")
    lh.add_argument("--wait", type=float, metavar="SECONDS", help="wait until RUNNING")

    h = sub.add_parser("herdr", help="control herdr on a node or inside a Slurm job")
    h.add_argument("--node"); h.add_argument("--cluster"); h.add_argument("--job")
    h.add_argument("--session", help="herdr session (default from inventory)")
    hs = h.add_subparsers(dest="action", required=True)
    for name in ("version", "status", "agents"):
        hs.add_parser(name)
    up = hs.add_parser("up", help="start a detached server on a plain node (recorded in the ledger)")
    up.add_argument("--run", help="run code name")
    dn = hs.add_parser("down", help="stop a server orchard started")
    dn.add_argument("--force", action="store_true", help="stop a server orchard did not start")
    g = hs.add_parser("get"); g.add_argument("target")
    r = hs.add_parser("read"); r.add_argument("target")
    r.add_argument("--lines", type=int, default=120)
    r.add_argument("--source", default="recent-unwrapped")
    pr = hs.add_parser("prompt"); pr.add_argument("target"); pr.add_argument("text")
    pr.add_argument("--no-wait", action="store_true"); pr.add_argument("--timeout-ms", type=int)
    w = hs.add_parser("wait"); w.add_argument("target")
    w.add_argument("--until", action="append"); w.add_argument("--timeout-ms", type=int)
    sa = hs.add_parser("start", help="new workspace at --cwd + named agent")
    sa.add_argument("name"); sa.add_argument("--kind", required=True); sa.add_argument("--cwd", required=True)
    sa.add_argument("--role", default="builder", help="builder | planner | reviewer | ... (ledger only)")
    sa.add_argument("--run", help="run code name (ledger only)")
    sa.add_argument("--over-budget", action="store_true", help="skip the fleet.max_agents check")
    sa.add_argument("agent_args", nargs="*", help="native agent args (put after --)")
    rv = hs.add_parser("review", help="start a different-model reviewer on a builder's work")
    rv.add_argument("builder", help="name of the agent whose work to review")
    rv.add_argument("--kind", help="reviewer kind (default fleet.roles.reviewer)")
    rv.add_argument("--name", help="reviewer name (default <builder>-rev)")
    rv.add_argument("--base", help="git ref to diff against, e.g. origin/main")
    rv.add_argument("--focus", help="extra review focus, appended to the prompt")
    rv.add_argument("--cwd", help="override the builder's cwd")
    rv.add_argument("--run"); rv.add_argument("--same-kind", action="store_true")
    rv.add_argument("--over-budget", action="store_true")
    rv.add_argument("--no-wait", action="store_true"); rv.add_argument("--timeout-ms", type=int)
    k = hs.add_parser("keys"); k.add_argument("target"); k.add_argument("keys", nargs="+")

    def fleet_args(x):
        x.add_argument("--target", action="append", metavar="SPEC",
                       help="extra target: node:<name> or job:<cluster>/<id>, repeatable")
        x.add_argument("--all-nodes", action="store_true", help="also ask every inventory node")

    fleet_args(sub.add_parser("fleet", help="every agent on every target, most urgent first"))
    wa = sub.add_parser("watch", help="poll the fleet; print one JSON event per change; notify")
    fleet_args(wa)
    wa.add_argument("--interval", type=float, default=30)
    wa.add_argument("--once", action="store_true", help="one poll (for cron)")
    wa.add_argument("--max-polls", type=int)
    wa.add_argument("--no-notify", action="store_true")
    wa.add_argument("--fresh", action="store_true", help="ignore the last saved poll; report everything now")
    dg = sub.add_parser("digest", help="markdown report of the fleet + screens of agents that need you")
    fleet_args(dg)
    dg.add_argument("--lines", type=int, default=40, help="screen lines per agent that needs you")
    dg.add_argument("--out", help="output file (default <state>/digests/YYYY-MM-DD_HHMM.md)")
    dg.add_argument("--notify", action="store_true", help="notify once if any agent needs you")
    cu = sub.add_parser("cleanup", help="stop what orchard started (dry run unless --yes)")
    cu.add_argument("--yes", action="store_true"); cu.add_argument("--run", help="only this run code name")
    lg = sub.add_parser("ledger", help="what orchard started (open targets)")
    lg.add_argument("--all", action="store_true", help="include closed targets")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s", stream=sys.stderr)
    try:
        out = run(a)
    except KeyboardInterrupt:
        return 130
    except (Exception,) as e:  # one JSON error shape for the agent
        print(json.dumps({"error": type(e).__name__, "message": str(e)}), file=sys.stderr)
        return 1
    if out is not STREAMED:
        print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
