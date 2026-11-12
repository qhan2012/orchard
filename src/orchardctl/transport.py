"""Command transports: where a shell command runs.

Every remote action in orchard is one shell command string run through a
Transport. This keeps the control plane small and easy to audit.

- SSHTransport  runs on a host through the system OpenSSH client, so
  ~/.ssh/config (ProxyJump, ControlMaster, keys, ssh-agent) applies unchanged.
- JobTransport  runs inside a running scheduler job, through the head/jumper:
  head$ srun --jobid=<id> --overlap ... bash -lc '<cmd>'   (Slurm default)
  The enter-the-job command is a template, so a Slurm-like scheduler works
  too. This needs no SSH access to compute nodes.
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


SLURM_JOB_EXEC = "srun --jobid={job} --overlap --nodes=1 --ntasks=1 bash -lc {cmd}"


@dataclass
class JobTransport:
    """Runs a command inside a running scheduler job, through the head/jumper.

    ``template`` is the head-side command that enters the job. Placeholders:
    {job} (job id) and {cmd} (the inner command). Both are shell-quoted.
    The Slurm default needs Slurm >= 20.11 for --overlap. A Slurm-like
    in-house scheduler sets its own template in inventory.yaml (job_exec).
    """

    head: Transport
    job_id: str
    template: str = SLURM_JOB_EXEC

    @property
    def name(self) -> str:
        return f"{self.head.name}/job:{self.job_id}"

    def wrap(self, cmd: str) -> str:
        return self.template.format(job=shlex.quote(self.job_id), cmd=shlex.quote(cmd))

    def run(self, cmd: str, input: str | None = None, timeout: float | None = None) -> Result:
        r = self.head.run(self.wrap(cmd), input=input, timeout=timeout)
        return Result(self.name, cmd, r.returncode, r.stdout, r.stderr)


def _s(b: bytes | str | None) -> str:
    if b is None:
        return ""
    return b if isinstance(b, str) else b.decode(errors="replace")
