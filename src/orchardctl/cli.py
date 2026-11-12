"""orchardctl: the command surface the master agent (or a human) uses.

All output is JSON on stdout so an agent can parse it. Errors print
{"error": ...} on stderr and exit 1.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shlex
import sys
import uuid
from pathlib import Path
from typing import Any

from . import inventory as inv_mod
from .herdr import HerdrClient
from .slurm import SlurmAdapter, herdr_job_script
from .transport import JobTransport, Transport

PROBE = (
    "echo host=$(hostname); echo user=$(whoami); "
    "echo load=\"$(cut -d' ' -f1-3 /proc/loadavg)\"; echo cpus=$(nproc); "
    "echo mem_mb=$(free -m | awk '/^Mem:/{print $2\"/\"$7\" total/avail\"}'); "
    "if command -v rocm-smi >/dev/null; then rocm-smi --showuse --showmemuse --csv 2>/dev/null "
    "| grep -i '^card' | sed 's/^/gpu=/'; "
    "elif command -v nvidia-smi >/dev/null; then nvidia-smi --query-gpu=index,name,utilization.gpu,"
    "memory.used,memory.total --format=csv,noheader | sed 's/^/gpu=/'; else echo gpu=none; fi; "
    "echo herdr=$(command -v herdr || echo missing); "
    "for a in claude codex opencode; do echo agent_$a=$(command -v $a || echo missing); done; "
    "for s in sbatch srun squeue; do command -v $s >/dev/null && echo sched_$s=$(command -v $s); done; true"
)

# Job ids: Slurm uses 123 or 123_4; a Slurm-like tool may differ. The id is
# always shell-quoted; this only rejects obvious garbage early.
_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


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


def _job_id(job: str) -> str:
    if not _JOB_ID.match(job):
        raise ValueError(f"bad job id {job!r}")
    return job


def _transport(inv: inv_mod.Inventory, name: str, job: str | None = None) -> Transport:
    """Where a command runs: a node; a cluster's head/jumper; or inside a job via the head."""
    t = inv.target(name)
    if job is None:
        return t.transport()
    if not isinstance(t, inv_mod.Cluster):
        raise ValueError(f"--job needs a cluster; {name!r} is a node")
    return JobTransport(t.transport(), _job_id(job), t.job_exec)


def _herdr(inv: inv_mod.Inventory, a: argparse.Namespace) -> HerdrClient:
    if a.node:
        t = inv.node(a.node).transport()
    elif a.cluster:  # with --job: inside the job; without: on the head/jumper
        t = _transport(inv, inv.cluster(a.cluster).name, a.job)
    else:
        raise SystemExit("herdr target: give --node NAME, or --cluster NAME [--job ID]")
    return HerdrClient(t, session=a.session or inv.herdr_session, binary=inv.herdr_binary)


def run(a: argparse.Namespace) -> Any:
    inv = inv_mod.load(inv_mod.resolve_path(a.inventory))

    if a.cmd == "inventory":
        return {
            "path": str(inv.path),
            "clusters": {k: v.__dict__ for k, v in inv.clusters.items()},
            "nodes": {k: v.__dict__ for k, v in inv.nodes.items()},
            "herdr": {"session": inv.herdr_session, "binary": inv.herdr_binary},
        }

    if a.cmd == "check":
        t = _transport(inv, a.target, a.job)
        r = t.run(PROBE, timeout=a.timeout)
        out = {"target": a.target, "where": t.name, "reachable": r.ok}
        return {**out, **(_kv(r.stdout) if r.ok else {"rc": r.returncode, "stderr": r.stderr.strip()})}

    if a.cmd == "exec":
        argv = a.command[1:] if a.command[:1] == ["--"] else a.command
        if not argv:
            raise SystemExit("exec: give a command after --")
        # One argument is a shell string (pipes, &&, globs work); several are quoted as argv.
        cmd = argv[0] if len(argv) == 1 else shlex.join(argv)
        t = _transport(inv, a.target, a.job)
        r = t.run(cmd, timeout=a.timeout)
        return {"target": a.target, "where": t.name, "cmd": cmd, "rc": r.returncode,
                "stdout": r.stdout, "stderr": r.stderr}

    if a.cmd == "slurm":
        c = inv.cluster(a.cluster)
        if c.scheduler != "slurm":
            raise SystemExit(f"cluster {c.name!r} uses scheduler {c.scheduler!r}; "
                             "slurm commands are not available there yet")
        s = SlurmAdapter(c.transport(), c.sbatch_defaults)
        if a.action == "queue":
            return [j.to_dict() for j in s.queue()]
        if a.action == "status":
            j = s.job(a.job)
            return j.to_dict() if j else {"job_id": a.job, "state": "NOT_FOUND"}
        if a.action == "cancel":
            return {"cancelled": s.cancel(a.job, force=a.force).to_dict()}
        if a.action == "submit":
            tag = a.tag or uuid.uuid4().hex[:8]
            job_id = s.submit(Path(a.script).read_text(), tag, **_opts(a.opt))
            return {"job_id": job_id, "tag": tag, "cluster": c.name}
        if a.action == "launch-herdr":
            session = a.session or inv.herdr_session
            tag = a.tag or f"herdr-{uuid.uuid4().hex[:8]}"
            opts = {"job-name": f"orchard-{session}", **_opts(a.opt)}
            job_id = s.submit(herdr_job_script(session, inv.herdr_binary), tag, **opts)
            out: dict[str, Any] = {"job_id": job_id, "tag": tag, "session": session}
            if a.wait:
                out["job"] = s.wait_running(job_id, timeout=a.wait).to_dict()
            return out

    if a.cmd == "herdr":
        h = _herdr(inv, a)
        act = a.action
        if act == "version":
            return {"version": h.version()}
        if act == "status":
            return h.server_status()
        if act == "up":
            return {"log": h.start_server()}
        if act == "down":
            return h.stop_server()
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
    p.add_argument("-v", "--verbose", action="store_true", help="log every remote command to stderr")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("inventory", help="show the parsed inventory")

    ck = sub.add_parser("check", help="probe a target: reachable, load, mem, GPU, herdr, agents, scheduler")
    ck.add_argument("target", help="node name, or cluster name (its head/jumper)")
    ck.add_argument("--job", help="probe inside this running job (cluster only)")
    ck.add_argument("--timeout", type=float, default=60)

    ex = sub.add_parser("exec", help="run one command on a target; JSON with rc/stdout/stderr")
    ex.add_argument("target", help="node name, or cluster name (its head/jumper)")
    ex.add_argument("--job", help="run inside this running job (cluster only)")
    ex.add_argument("--timeout", type=float, help="seconds; rc 124 on timeout")
    ex.add_argument("command", nargs="*",
                    help="put it after --: one shell string, or argv words")

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

    h = sub.add_parser("herdr", help="control herdr on a node, a cluster head/jumper, or inside a job")
    h.add_argument("--node"); h.add_argument("--cluster"); h.add_argument("--job")
    h.add_argument("--session", help="herdr session (default from inventory)")
    hs = h.add_subparsers(dest="action", required=True)
    for name in ("version", "status", "up", "down", "agents"):
        hs.add_parser(name)
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
