"""Fleet: one view of every agent orchard can reach, sorted by who needs you.

This is the multi-machine form of what herdr gives inside one session (a bell
when an agent needs a decision, a mark when it is working). The human is the
bottleneck, so the board answers one question first: which agent is waiting
for me?

Attention order (lower = more urgent):
    blocked  - an approval or question dialog is open; a person must look
    done     - finished, output not yet looked at
    unknown  - herdr cannot classify the agent; treat as needing a look
    idle     - ready, nothing new
    working  - leave it alone

herdr facts used (github.com/ogulcancelik/herdr @ ee5bfb5, src/api/schema):
- ``agent list`` -> {"result": {"type": "agent_list", "agents": [AgentInfo]}}
- AgentInfo has name, agent (kind), agent_status, pane_id, cwd,
  state_change_seq, completion_seq.
- ``done`` turns into ``idle`` only after an explicit focus. Reads do not mark
  it seen, so orchard never clears the human's "done" signal by watching.
"""

from __future__ import annotations

import logging
import shlex
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .herdr import HerdrClient

log = logging.getLogger(__name__)

ATTENTION = {"blocked": 0, "done": 1, "unknown": 2, "idle": 3, "working": 4}
NEEDS_YOU = {"blocked", "done", "unknown"}
EVENT_FOR = {"blocked": "needs_decision", "done": "finished", "unknown": "unclassified"}


@dataclass(frozen=True)
class Target:
    """Where a herdr server lives: a plain node, or a running Slurm job."""

    kind: str  # "node" | "job"
    node: str | None = None
    cluster: str | None = None
    job: str | None = None

    @property
    def key(self) -> str:
        return f"node:{self.node}" if self.kind == "node" else f"job:{self.cluster}/{self.job}"

    @classmethod
    def parse(cls, spec: str) -> "Target":
        """``node:<name>`` or ``job:<cluster>/<id>`` (the ledger key format)."""
        kind, _, rest = spec.partition(":")
        if kind == "node" and rest:
            return cls("node", node=rest)
        if kind == "job" and "/" in rest:
            cluster, _, job = rest.partition("/")
            if cluster and job:
                return cls("job", cluster=cluster, job=job)
        raise ValueError(f"bad target {spec!r}: use node:<name> or job:<cluster>/<id>")


ClientFor = Callable[[Target, str | None], HerdrClient]


# -- snapshot -----------------------------------------------------------------
def agents_of(payload: Any) -> list[dict[str, Any]]:
    """Pull the agent list out of an ``agent list`` reply, old or new shape."""
    if isinstance(payload, dict):
        res = payload.get("result", payload)
        if isinstance(res, dict) and isinstance(res.get("agents"), list):
            return res["agents"]
    if isinstance(payload, list):
        return payload
    raise ValueError(f"unexpected agent list reply: {str(payload)[:200]}")


def row(target: str, a: dict[str, Any], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    status = str(a.get("agent_status") or "unknown")
    meta = meta or {}
    return {
        "target": target,
        "name": a.get("name") or a.get("pane_id"),
        "kind": a.get("agent") or a.get("display_agent"),
        "status": status,
        "needs_you": status in NEEDS_YOU,
        "seq": a.get("state_change_seq"),
        "cwd": a.get("cwd") or a.get("foreground_cwd"),
        "pane_id": a.get("pane_id"),
        "role": meta.get("role"),
        "run": meta.get("run"),
        "of": meta.get("of"),
    }


def snapshot(targets: Iterable[tuple[Target, str | None]], client_for: ClientFor,
             meta: Callable[[str, str], dict[str, Any] | None] = lambda k, n: None) -> dict[str, Any]:
    """Ask every target for its agents. One bad target never hides the others."""
    rows: list[dict[str, Any]] = []
    status: list[dict[str, Any]] = []
    for t, session in targets:
        try:
            agents = agents_of(client_for(t, session).agents())
        except Exception as e:  # unreachable node, job ended, herdr down
            status.append({"target": t.key, "ok": False, "error": f"{type(e).__name__}: {e}"[:300]})
            continue
        status.append({"target": t.key, "ok": True, "agents": len(agents)})
        rows += [row(t.key, a, meta(t.key, a.get("name") or "")) for a in agents]
    rows.sort(key=lambda r: (ATTENTION.get(r["status"], 2), r["target"], str(r["name"])))
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "needs_you": sum(1 for r in rows if r["needs_you"]),
        "live_agents": len(rows),
        "counts": counts,
        "agents": rows,
        "targets": status,
    }


# -- watch --------------------------------------------------------------------
def diff(prev: dict[str, Any] | None, cur: dict[str, Any]) -> list[dict[str, Any]]:
    """Events for agents that newly need a person, vanished, or lost contact.

    An event fires on a change of (status, state_change_seq), so a ``done``
    that nobody has looked at fires once, not on every poll.
    """
    def by_key(snap):
        return {(r["target"], r["name"]): r for r in (snap or {}).get("agents", [])}

    def bad(snap):
        return {t["target"]: t for t in (snap or {}).get("targets", []) if not t["ok"]}

    old, new = by_key(prev), by_key(cur)
    events = []
    for k, r in new.items():
        if r["status"] not in EVENT_FOR:
            continue
        o = old.get(k)
        if o is None or (o["status"], o["seq"]) != (r["status"], r["seq"]):
            events.append({"event": EVENT_FOR[r["status"]], **_brief(r)})
    if prev is not None:
        for k, o in old.items():
            if k not in new and o["target"] not in bad(cur):
                events.append({"event": "agent_gone", **_brief(o)})
    old_bad = bad(prev)
    for key, t in bad(cur).items():
        if key not in old_bad:
            events.append({"event": "target_unreachable", "target": key, "error": t["error"]})
    return events


def _brief(r: dict[str, Any]) -> dict[str, Any]:
    return {k: r[k] for k in ("target", "name", "kind", "status", "role", "cwd") if r.get(k) is not None}


def notify(command: list[str] | None, event: dict[str, Any], timeout: float = 10) -> dict[str, Any] | None:
    """Run the inventory's notify command for one event. Never raises.

    ``command`` is an argv template, run without a shell. Placeholders:
    {title} {body} {event} {target} {name} {status}.
    """
    if not command:
        return None
    title = f"orchard: {event.get('name') or event.get('target')} {event['event'].replace('_', ' ')}"
    body = " ".join(f"{k}={event[k]}" for k in ("target", "kind", "role", "cwd", "error") if event.get(k))
    fields = {"title": title, "body": body, "event": event["event"], "target": event.get("target", ""),
              "name": event.get("name") or "", "status": event.get("status") or ""}
    argv = [part.format(**fields) for part in command]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return {"notify_rc": p.returncode, **({"notify_err": p.stderr.strip()[:200]} if p.returncode else {})}
    except Exception as e:  # a broken notifier must not stop the watch loop
        log.warning("notify failed: %s", e)
        return {"notify_rc": None, "notify_err": f"{type(e).__name__}: {e}"[:200]}


# -- digest -------------------------------------------------------------------
def render_digest(snap: dict[str, Any], tails: dict[tuple[str, str], str]) -> str:
    """Markdown for a person who has five minutes: what needs you, then the rest."""
    c = snap["counts"]
    lines = [
        f"# orchard digest {snap['ts']}",
        "",
        f"**{snap['needs_you']} need you** · {snap['live_agents']} live · "
        + ", ".join(f"{k} {c[k]}" for k in sorted(c, key=lambda s: ATTENTION.get(s, 2))),
        "",
    ]
    down = [t for t in snap["targets"] if not t["ok"]]
    if down:
        lines += ["## Unreachable targets", ""]
        lines += [f"- `{t['target']}`: {t['error']}" for t in down]
        lines.append("")
    lines += ["## Agents", "", "| Status | Target | Agent | Kind | Role | cwd |", "|---|---|---|---|---|---|"]
    for r in snap["agents"]:
        role = r["role"] or ""
        if r.get("of"):
            role += f" of {r['of']}"
        lines.append(f"| {r['status']} | `{r['target']}` | {r['name']} | {r['kind'] or ''} | {role} | "
                     f"{r['cwd'] or ''} |")
    for (target, name), text in tails.items():
        lines += ["", f"### {name} @ `{target}`", "", "```text", text.rstrip(), "```"]
    return "\n".join(lines) + "\n"


# -- maker / checker ------------------------------------------------------------
REVIEW_PROMPT = (
    "You are the reviewer. Another agent ({builder_kind}, named {builder}) made the change in this "
    "directory. Do not edit any file. Review {scope}. Check correctness first, then tests, then "
    "simplicity. Report only actionable findings, most severe first. For each: file:line, the "
    "concrete failure scenario, and the fix. If tests exist, run them and report the result. "
    "End with exactly one line: VERDICT: ship | fix-first | rework.{focus}"
)


def review_prompt(builder: str, builder_kind: str | None, base: str | None, focus: str | None) -> str:
    if base:
        scope = (f"`git diff {shlex.quote(base)}...HEAD` plus any uncommitted change "
                 "(`git status`, `git diff HEAD`)")
    else:
        scope = ("the uncommitted change (`git status`, `git diff HEAD`) and any commit the builder "
                 "made that is not on the upstream branch (`git log @{upstream}..HEAD` if an upstream exists)")
    return REVIEW_PROMPT.format(builder=builder, builder_kind=builder_kind or "unknown kind", scope=scope,
                                focus=f" Focus: {focus}" if focus else "")


def reviewer_name(builder: str) -> str:
    return (builder[:28] + "-rev")[:32]
