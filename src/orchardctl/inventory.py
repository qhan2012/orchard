"""Inventory: the clusters and nodes orchard may touch.

All site-specific values (hosts, partitions, sessions) live in the inventory
file, never in code. Lookup order: --inventory, $ORCHARD_INVENTORY,
./inventory.yaml.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .transport import SLURM_JOB_EXEC, SSHTransport

SCHEDULERS = {"slurm", "custom"}  # custom: a Slurm-like tool; set job_exec


class InventoryError(ValueError):
    pass


@dataclass
class Cluster:
    name: str
    head: str  # ssh host or alias of the login/head node
    scheduler: str = "slurm"
    sbatch_defaults: dict[str, str] = field(default_factory=dict)
    job_exec: str = SLURM_JOB_EXEC  # head-side command that runs {cmd} inside job {job}
    ssh_options: list[str] = field(default_factory=list)

    def transport(self) -> SSHTransport:
        return SSHTransport(self.head, self.ssh_options)


@dataclass
class Node:
    name: str
    host: str
    ssh_options: list[str] = field(default_factory=list)

    def transport(self) -> SSHTransport:
        return SSHTransport(self.host, self.ssh_options)


@dataclass
class Inventory:
    path: Path
    clusters: dict[str, Cluster]
    nodes: dict[str, Node]
    herdr_session: str
    herdr_binary: str

    def cluster(self, name: str) -> Cluster:
        try:
            return self.clusters[name]
        except KeyError:
            raise InventoryError(f"unknown cluster {name!r}; known: {sorted(self.clusters)}")

    def target(self, name: str) -> "Cluster | Node":
        """A node, or a cluster (its head/jumper), by name."""
        if name in self.nodes:
            return self.nodes[name]
        if name in self.clusters:
            return self.clusters[name]
        raise InventoryError(f"unknown target {name!r}; nodes: {sorted(self.nodes)}, "
                             f"clusters: {sorted(self.clusters)}")

    def node(self, name: str) -> Node:
        try:
            return self.nodes[name]
        except KeyError:
            raise InventoryError(f"unknown node {name!r}; known: {sorted(self.nodes)}")


def resolve_path(explicit: str | None) -> Path:
    p = explicit or os.environ.get("ORCHARD_INVENTORY") or "inventory.yaml"
    return Path(p).expanduser()


def load(path: str | Path) -> Inventory:
    path = Path(path)
    if not path.is_file():
        raise InventoryError(f"inventory not found: {path} (copy inventory.example.yaml)")
    data = yaml.safe_load(path.read_text()) or {}
    return parse(data, path)


def parse(data: dict, path: Path = Path("<memory>")) -> Inventory:
    defaults = data.get("defaults") or {}
    base_opts = list(defaults.get("ssh_options") or [])

    clusters: dict[str, Cluster] = {}
    for name, c in (data.get("clusters") or {}).items():
        if not c or "head" not in c:
            raise InventoryError(f"cluster {name!r}: 'head' is required")
        sched = c.get("scheduler", "slurm")
        if sched not in SCHEDULERS:
            raise InventoryError(f"cluster {name!r}: scheduler {sched!r} not supported {sorted(SCHEDULERS)}")
        job_exec = c.get("job_exec")
        if sched == "custom" and not job_exec:
            raise InventoryError(f"cluster {name!r}: scheduler 'custom' needs job_exec")
        job_exec = str(job_exec or SLURM_JOB_EXEC)
        for ph in ("{job}", "{cmd}"):
            if ph not in job_exec:
                raise InventoryError(f"cluster {name!r}: job_exec must contain {ph}")
        clusters[name] = Cluster(
            name=name,
            head=str(c["head"]),
            scheduler=sched,
            sbatch_defaults={k: str(v) for k, v in (c.get("sbatch_defaults") or {}).items()},
            job_exec=job_exec,
            ssh_options=base_opts + list(c.get("ssh_options") or []),
        )

    nodes: dict[str, Node] = {}
    for name, n in (data.get("nodes") or {}).items():
        if not n or "host" not in n:
            raise InventoryError(f"node {name!r}: 'host' is required")
        nodes[name] = Node(name, str(n["host"]), base_opts + list(n.get("ssh_options") or []))

    both = sorted(set(clusters) & set(nodes))
    if both:
        raise InventoryError(f"names used for both a cluster and a node: {both}")

    herdr = data.get("herdr") or {}
    return Inventory(
        path=path,
        clusters=clusters,
        nodes=nodes,
        herdr_session=str(herdr.get("session", "orchard")),
        herdr_binary=str(herdr.get("binary", "herdr")),
    )
