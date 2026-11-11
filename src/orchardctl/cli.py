"""orchardctl: the command surface the master agent (or a human) uses.

All output is JSON on stdout so an agent can parse it. Errors print
{"error": ...} on stderr and exit 1.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from . import inventory as inv_mod
from .herdr import HerdrClient
from .registry import ORCHARD, USER, Registry, target_id
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


def _target(inv: inv_mod.Inventory, a: argparse.Namespace) -> dict[str, Any]:
    """Check a --node / --cluster --job target against the inventory."""
    session = a.session or inv.herdr_session
    if a.node:
        inv.node(a.node)
        return {"session": session, "node": a.node}
    if a.cluster and a.job:
        inv.cluster(a.cluster)
        return {"session": session, "cluster": a.cluster, "job_id": check_job_id(a.job)}
    raise SystemExit("target: give --node NAME, or --cluster NAME --job ID")


def _herdr(inv: inv_mod.Inventory, tgt: dict[str, Any]) -> HerdrClient:
    if tgt.get("node"):
        t = inv.node(tgt["node"]).transport()
    else:
        t = SrunTransport(inv.cluster(tgt["cluster"]).transport(), tgt["job_id"])
    return HerdrClient(t, session=tgt["session"], binary=inv.herdr_binary)


def _state_dir(a: argparse.Namespace, inv: inv_mod.Inventory) -> Path:
    explicit = a.state_dir or os.environ.get("ORCHARD_STATE_DIR")
    return Path(explicit).expanduser() if explicit else inv.path.parent / "state"


def run(a: argparse.Namespace) -> Any:
    inv = inv_mod.load(inv_mod.resolve_path(a.inventory))
    reg = Registry(_state_dir(a, inv))

    if a.cmd == "inventory":
        return {
            "path": str(inv.path),
            "clusters": {k: v.__dict__ for k, v in inv.clusters.items()},
            "nodes": {k: v.__dict__ for k, v in inv.nodes.items()},
            "herdr": {"session": inv.herdr_session, "binary": inv.herdr_binary},
        }

    if a.cmd == "session":
        if a.action == "list":
            return {"path": str(reg.path),
                    "sessions": [asdict(e) for e in reg.list(include_ended=a.all)]}
        if a.action == "adopt":
            return asdict(reg.record(USER, note=a.note or "", **_target(inv, a)))
        if a.action == "forget":
            return {"forgotten": asdict(reg.forget(a.id))}

    if a.cmd == "node":
        r = inv.node(a.name).transport().run(NODE_PROBE, timeout=a.timeout)
        return {"node": a.name, "reachable": r.ok, **(_kv(r.stdout) if r.ok else {"stderr": r.stderr.strip()})}

    if a.cmd == "slurm":
        c = inv.cluster(a.cluster)
        s = SlurmAdapter(c.transport(), c.sbatch_defaults)
        if a.action == "queue":
            return [j.to_dict() for j in s.queue()]
        if a.action == "status":
            j = s.job(a.job)
            return j.to_dict() if j else {"job_id": a.job, "state": "NOT_FOUND"}
        if a.action == "cancel":
            job = s.cancel(a.job, force=a.force)
            return {"cancelled": job.to_dict(), "sessions_ended": reg.end_job(c.name, job.job_id)}
        if a.action == "submit":
            tag = a.tag or uuid.uuid4().hex[:8]
            job_id = s.submit(Path(a.script).read_text(), tag, **_opts(a.opt))
            return {"job_id": job_id, "tag": tag, "cluster": c.name}
        if a.action == "launch-herdr":
            session = a.session or inv.herdr_session
            tag = a.tag or f"herdr-{uuid.uuid4().hex[:8]}"
            opts = {"job-name": f"orchard-{session}", **_opts(a.opt)}
            job_id = s.submit(herdr_job_script(session, inv.herdr_binary), tag, **opts)
            entry = reg.record(ORCHARD, session, cluster=c.name, job_id=job_id, tag=tag)
            out: dict[str, Any] = {"job_id": job_id, "tag": tag, "session": session,
                                   "registry_id": entry.id}
            if a.wait:
                out["job"] = s.wait_running(job_id, timeout=a.wait).to_dict()
            return out

    if a.cmd == "herdr":
        tgt = _target(inv, a)
        tid = target_id(**tgt)
        h = _herdr(inv, tgt)
        act = a.action
        if act == "version":
            return {"version": h.version()}
        if act == "status":
            return h.server_status()
        if act == "up":
            if not tgt.get("node"):
                raise SystemExit("herdr up is for plain nodes; on Slurm use `slurm <c> launch-herdr`")
            reg.check_can_record(tid, ORCHARD)  # refuse before any remote command
            log = h.start_server()
            return {"log": log, "registry_id": reg.record(ORCHARD, **tgt).id}
        if act == "down":
            # Stopping a server ends every agent in it: orchard-started only.
            if not a.force:
                reg.require_orchard(tid)
            out = h.stop_server()
            reg.end(tid)
            return {"stopped": tid, "result": out}
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
            return h.start_agent(a.name, a.kind, a.cwd, agent_args=a.agent_args)
        if act == "keys":
            return h.send_keys(a.target, *a.keys)

    raise SystemExit(f"unhandled command {a.cmd}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="orchardctl", description=__doc__)
    p.add_argument("--inventory", help="inventory file (default $ORCHARD_INVENTORY or ./inventory.yaml)")
    p.add_argument("--state-dir", help="registry dir (default $ORCHARD_STATE_DIR or <inventory dir>/state)")
    p.add_argument("-v", "--verbose", action="store_true", help="log every remote command to stderr")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("inventory", help="show the parsed inventory")

    se = sub.add_parser("session", help="registry of herdr sessions and who started each")
    ses = se.add_subparsers(dest="action", required=True)
    sl = ses.add_parser("list"); sl.add_argument("--all", action="store_true", help="include ended sessions")
    ad = ses.add_parser("adopt", help="register a herdr session that a person started")
    ad.add_argument("--node"); ad.add_argument("--cluster"); ad.add_argument("--job")
    ad.add_argument("--session", help="herdr session (default from inventory)")
    ad.add_argument("--note")
    fo = ses.add_parser("forget", help="delete a registry record (touches nothing remote)")
    fo.add_argument("id")

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
    lh.add_argument("--session"); lh.add_argument("--tag")
    lh.add_argument("--opt", action="append", metavar="KEY=VALUE")
    lh.add_argument("--wait", type=float, metavar="SECONDS", help="wait until RUNNING")

    h = sub.add_parser("herdr", help="control herdr on a node or inside a Slurm job")
    h.add_argument("--node"); h.add_argument("--cluster"); h.add_argument("--job")
    h.add_argument("--session", help="herdr session (default from inventory)")
    hs = h.add_subparsers(dest="action", required=True)
    for name in ("version", "status", "up", "agents"):
        hs.add_parser(name)
    dn = hs.add_parser("down", help="stop a herdr server that orchard started")
    dn.add_argument("--force", action="store_true", help="also stop a server orchard did not start")
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
    sa.add_argument("agent_args", nargs="*", help="native agent args (put after --)")
    k = hs.add_parser("keys"); k.add_argument("target"); k.add_argument("keys", nargs="+")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s", stream=sys.stderr)
    try:
        out = run(a)
    except (Exception,) as e:  # one JSON error shape for the agent
        print(json.dumps({"error": type(e).__name__, "message": str(e)}), file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
