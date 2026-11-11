"""Session registry: which herdr sessions the master knows, and who started each.

The registry is a local record (state/sessions.json, gitignored). It is not
live state: the target (`squeue`, `herdr status`) is ground truth. Its job is
the ownership rule: orchard stops only the herdr servers that orchard started.

started_by:
- "orchard": orchard started it (`slurm launch-herdr`, `herdr up`).
- "user":    a person started it; the master only watches and prompts
             (`session adopt`).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ORCHARD = "orchard"
USER = "user"
VERSION = 1


class RegistryError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Entry:
    id: str
    session: str
    started_by: str
    node: str | None = None
    cluster: str | None = None
    job_id: str | None = None
    tag: str | None = None
    note: str = ""
    created_at: str = ""
    ended_at: str | None = None

    @property
    def live(self) -> bool:
        return self.ended_at is None


def target_id(session: str, node: str | None = None, cluster: str | None = None,
              job_id: str | None = None) -> str:
    if node:
        return f"node:{node}/{session}"
    if cluster and job_id:
        return f"job:{cluster}/{job_id}/{session}"
    raise RegistryError("target needs a node, or a cluster and a job id")


class Registry:
    def __init__(self, state_dir: str | Path):
        self.path = Path(state_dir) / "sessions.json"

    # -- storage ----------------------------------------------------------
    def _load(self) -> dict[str, Entry]:
        if not self.path.is_file():
            return {}
        data = json.loads(self.path.read_text())
        if data.get("version") != VERSION:
            raise RegistryError(f"{self.path}: unsupported version {data.get('version')!r}")
        return {e["id"]: Entry(**e) for e in data.get("sessions", [])}

    def _save(self, entries: dict[str, Entry]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = {"version": VERSION, "sessions": [asdict(e) for e in entries.values()]}
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".sessions-")
        with os.fdopen(fd, "w") as f:
            json.dump(body, f, indent=2)
            f.write("\n")
        os.replace(tmp, self.path)  # atomic: a crash never leaves half a file

    # -- queries ----------------------------------------------------------
    def list(self, include_ended: bool = False) -> list[Entry]:
        return [e for e in self._load().values() if include_ended or e.live]

    def get(self, id: str) -> Entry | None:
        return self._load().get(id)

    def check_can_record(self, id: str, started_by: str) -> None:
        e = self.get(id)
        if e and e.live and e.started_by != started_by:
            raise RegistryError(
                f"{id} is already registered as started by {e.started_by}. "
                "If that record is stale, run `orchardctl session forget` first."
            )

    def require_orchard(self, id: str) -> Entry:
        e = self.get(id)
        if e is None or not e.live:
            raise RegistryError(
                f"{id} is not in the registry, so orchard did not start it. "
                "Use --force only after a person confirms."
            )
        if e.started_by != ORCHARD:
            raise RegistryError(
                f"{id} was started by {e.started_by}, not by orchard. "
                "Use --force only after a person confirms."
            )
        return e

    # -- changes ----------------------------------------------------------
    def record(self, started_by: str, session: str, node: str | None = None,
               cluster: str | None = None, job_id: str | None = None,
               tag: str | None = None, note: str = "") -> Entry:
        if started_by not in (ORCHARD, USER):
            raise RegistryError(f"bad started_by {started_by!r}")
        id = target_id(session, node, cluster, job_id)
        self.check_can_record(id, started_by)
        entries = self._load()
        old = entries.get(id)
        if old and old.live:  # same owner: keep the first record, refresh details
            old.tag = tag or old.tag
            old.note = note or old.note
            entry = old
        else:
            entry = Entry(id, session, started_by, node, cluster, job_id, tag, note, _now())
            entries[id] = entry
        self._save(entries)
        return entry

    def end(self, id: str) -> Entry | None:
        entries = self._load()
        e = entries.get(id)
        if e and e.live:
            e.ended_at = _now()
            self._save(entries)
        return e

    def end_job(self, cluster: str, job_id: str) -> list[str]:
        entries = self._load()
        ended = []
        for e in entries.values():
            if e.live and e.cluster == cluster and e.job_id == job_id:
                e.ended_at = _now()
                ended.append(e.id)
        if ended:
            self._save(entries)
        return ended

    def forget(self, id: str) -> Entry:
        entries = self._load()
        if id not in entries:
            raise RegistryError(f"{id} is not in the registry")
        e = entries.pop(id)
        self._save(entries)
        return e
