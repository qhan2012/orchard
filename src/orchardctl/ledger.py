"""Ledger: an append-only record of what orchard started.

One JSON object per line in ``state/ledger.jsonl`` (gitignored). The ledger
answers three questions without asking the remote side to remember anything:

- Which targets (Slurm jobs, herdr servers on plain nodes) did orchard start?
  The fleet board and the cleanup command walk this list.
- Did orchard start this herdr server? ``herdr down`` refuses otherwise.
- Which agent has which role (builder, reviewer, ...) and which run code name?

The ledger is a local record, not ground truth. Live state on the target
(``squeue``, ``herdr agent list``) always wins; the fleet board reports a
target that the ledger lists but the remote side no longer has.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

OPEN_EVENTS = {"job_launched", "server_up"}
CLOSE_EVENTS = {"job_cancelled", "server_down", "target_gone"}


def job_key(cluster: str, job_id: str) -> str:
    return f"job:{cluster}/{job_id}"


def node_key(node: str) -> str:
    return f"node:{node}"


@dataclass
class TargetRecord:
    key: str
    session: str
    opened: str
    run: str | None = None
    closed: str | None = None
    owned: bool = True  # False: orchard started agents here, not the server/job
    agents: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def open(self) -> bool:
        return self.closed is None

    def to_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "open": self.open}


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    # -- write ------------------------------------------------------------
    def record(self, event: str, target: str, **fields: Any) -> dict[str, Any]:
        entry = {"ts": _now(), "event": event, "target": target,
                 **{k: v for k, v in fields.items() if v is not None}}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    # -- read -------------------------------------------------------------
    def entries(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        out = []
        for n, line in enumerate(self.path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{self.path}:{n}: bad ledger line: {e}") from e
        return out

    def targets(self) -> dict[str, TargetRecord]:
        """Fold the event log into one record per target. Last event wins."""
        return fold(self.entries())

    def open_targets(self) -> list[TargetRecord]:
        return [t for t in self.targets().values() if t.open]

    def started(self, key: str) -> bool:
        """True if orchard opened this target (job or server) and has not closed it."""
        t = self.targets().get(key)
        return bool(t and t.open and t.owned)

    def agent(self, key: str, name: str) -> dict[str, Any] | None:
        t = self.targets().get(key)
        return t.agents.get(name) if t else None


def fold(entries: Iterable[dict[str, Any]]) -> dict[str, TargetRecord]:
    targets: dict[str, TargetRecord] = {}
    for e in entries:
        key, ev = e["target"], e["event"]
        if ev in OPEN_EVENTS:
            # A re-opened key (new server on the same node) starts fresh.
            targets[key] = TargetRecord(key, e.get("session", ""), e["ts"], run=e.get("run"))
        elif ev in CLOSE_EVENTS and key in targets:
            targets[key].closed = e["ts"]
        elif ev == "agent_started":
            t = targets.get(key)
            if t is None:
                # Agent on a server orchard did not start: track the agent only.
                t = targets[key] = TargetRecord(key, e.get("session", ""), e["ts"], owned=False)
            t.agents[e["name"]] = {k: e.get(k) for k in ("kind", "role", "cwd", "run", "of")}
            t.agents[e["name"]]["started"] = e["ts"]
    return targets


def default_path(inventory_path: Path) -> Path:
    env = os.environ.get("ORCHARD_STATE")
    base = Path(env).expanduser() if env else inventory_path.resolve().parent / "state"
    return base / "ledger.jsonl"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")
