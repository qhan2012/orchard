"""Command transports: where a shell command runs.

Every remote action in orchard is one shell command string run through a
Transport. This keeps the control plane small and easy to audit.

- SSHTransport  runs on a host through the system OpenSSH client, so
  ~/.ssh/config (ProxyJump, ControlMaster, keys, ssh-agent) applies unchanged.
- SrunTransport runs inside a running Slurm job, through the cluster head:
  head$ srun --jobid=<id> --overlap ... bash -lc '<cmd>'
  This needs no SSH access to compute nodes.
"""

from __future__ import annotations

import logging
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Protocol

log = logging.getLogger(__name__)


class CommandError(RuntimeError):
    def __init__(self, result: "Result"):
        self.result = result
        super().__init__(
            f"[{result.where}] exit {result.returncode}: {result.cmd}\n{result.stderr.strip()}"
        )


@dataclass
class Result:
    where: str
    cmd: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def check(self) -> "Result":
        if not self.ok:
            raise CommandError(self)
        return self


class Transport(Protocol):
    name: str

    def run(self, cmd: str, input: str | None = None, timeout: float | None = None) -> Result: ...


@dataclass
class SSHTransport:
    host: str
    ssh_options: list[str] = field(default_factory=list)
    connect_timeout: int = 10

    @property
    def name(self) -> str:
        return f"ssh:{self.host}"

    def argv(self, cmd: str) -> list[str]:
        # BatchMode: never block on a password prompt; fail fast instead.
        return [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={self.connect_timeout}",
            *self.ssh_options,
            self.host,
            "--",
            cmd,
        ]

    def run(self, cmd: str, input: str | None = None, timeout: float | None = None) -> Result:
        log.debug("%s $ %s", self.name, cmd)
        try:
            p = subprocess.run(
                self.argv(cmd), input=input, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired as e:
            return Result(self.name, cmd, 124, _s(e.stdout), f"timeout after {timeout}s")
        return Result(self.name, cmd, p.returncode, p.stdout, p.stderr)


@dataclass
class SrunTransport:
    head: Transport
    job_id: str

    @property
    def name(self) -> str:
        return f"{self.head.name}/job:{self.job_id}"

    def wrap(self, cmd: str) -> str:
        # --overlap (Slurm >= 20.11) shares the job's resources with the
        # already-running step instead of waiting for free resources.
        return (
            f"srun --jobid={shlex.quote(self.job_id)} --overlap --nodes=1 --ntasks=1 "
            f"bash -lc {shlex.quote(cmd)}"
        )

    def run(self, cmd: str, input: str | None = None, timeout: float | None = None) -> Result:
        r = self.head.run(self.wrap(cmd), input=input, timeout=timeout)
        return Result(self.name, cmd, r.returncode, r.stdout, r.stderr)


def _s(b: bytes | str | None) -> str:
    if b is None:
        return ""
    return b if isinstance(b, str) else b.decode(errors="replace")
