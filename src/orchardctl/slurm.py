"""Slurm adapter. Every Slurm command runs on the cluster head over SSH.

Ownership rule: orchard tags each job it submits with --comment=orchard:<tag>.
cancel() only acts on jobs in `squeue --me` (your user) that carry the tag,
unless force=True.
"""

from __future__ import annotations

import re
import shlex
import time
from dataclasses import dataclass

from .transport import Transport

TAG_PREFIX = "orchard:"
_OPT_KEY = re.compile(r"^[a-z][a-z0-9-]*$")
_JOB_ID = re.compile(r"^\d+(_\d+)?$")
SQUEUE_FMT = "%i|%j|%T|%M|%N|%k"  # id|name|state|elapsed|nodelist|comment
ACTIVE = {"PENDING", "CONFIGURING", "RUNNING", "COMPLETING", "SUSPENDED", "REQUEUED", "RESIZING"}


class SlurmError(RuntimeError):
    pass


class OwnershipError(SlurmError):
    pass


@dataclass
class Job:
    job_id: str
    name: str
    state: str
    elapsed: str
    nodes: str
    comment: str = ""

    @property
    def owned(self) -> bool:
        return self.comment.startswith(TAG_PREFIX)

    @property
    def active(self) -> bool:
        return self.state.split()[0] in ACTIVE

    def to_dict(self) -> dict:
        return {**self.__dict__, "owned": self.owned}


def sbatch_args(opts: dict[str, str]) -> list[str]:
    out = []
    for k, v in opts.items():
        if not _OPT_KEY.match(k):
            raise SlurmError(f"bad sbatch option name {k!r}")
        out.append(f"--{k}={v}")
    return out


def check_job_id(job_id: str) -> str:
    if not _JOB_ID.match(job_id):
        raise SlurmError(f"bad job id {job_id!r}")
    return job_id


class SlurmAdapter:
    def __init__(self, head: Transport, defaults: dict[str, str] | None = None):
        self.head = head
        self.defaults = dict(defaults or {})

    def submit(self, script: str, tag: str, **opts: str) -> str:
        """Submit a batch script (sent on stdin). Returns the job id."""
        merged = {**self.defaults, **opts, "comment": f"{TAG_PREFIX}{tag}"}
        cmd = " ".join(["sbatch", "--parsable", *map(shlex.quote, sbatch_args(merged))])
        out = self.head.run(cmd, input=script).check().stdout.strip()
        job_id = out.split(";")[0]  # --parsable prints "id" or "id;cluster"
        if not _JOB_ID.match(job_id):
            raise SlurmError(f"unexpected sbatch output: {out!r}")
        return job_id

    def queue(self, job_id: str | None = None) -> list[Job]:
        """Your jobs in the live queue (squeue --me)."""
        cmd = f"squeue --me --noheader --format={shlex.quote(SQUEUE_FMT)}"
        if job_id:
            cmd += f" --jobs={check_job_id(job_id)}"
        r = self.head.run(cmd)
        if not r.ok:
            # squeue errors on an id that already left the queue.
            if job_id and "Invalid job id" in r.stderr:
                return []
            r.check()
        jobs = [parse_squeue_line(l) for l in r.stdout.splitlines() if l.strip()]
        # Never trust row order: keep only the exact id asked for.
        return [j for j in jobs if j.job_id == job_id] if job_id else jobs

    def job(self, job_id: str) -> Job | None:
        """Live state from squeue, else final state from sacct."""
        live = self.queue(job_id)
        if live:
            return live[0]
        cmd = (
            f"sacct -j {check_job_id(job_id)} -X -P -n "
            "-o JobID,JobName,State,Elapsed,NodeList,Comment"
        )
        r = self.head.run(cmd).check()
        for line in r.stdout.splitlines():
            if line.strip():
                j = parse_squeue_line(line)
                if j.job_id == job_id:
                    return j
        return None

    def cancel(self, job_id: str, force: bool = False) -> Job:
        check_job_id(job_id)
        jobs = self.queue(job_id)
        if not jobs:
            raise OwnershipError(f"job {job_id} is not in your live queue (squeue --me)")
        job = jobs[0]
        if not job.owned and not force:
            raise OwnershipError(
                f"job {job_id} has no {TAG_PREFIX} tag (comment={job.comment!r}); "
                "orchard did not submit it. Use --force only after you confirm ownership."
            )
        self.head.run(f"scancel {job_id}").check()
        return job

    def wait_running(self, job_id: str, timeout: float, poll: float = 10.0) -> Job:
        deadline = time.monotonic() + timeout
        while True:
            job = self.job(job_id)
            if job is None:
                raise SlurmError(f"job {job_id} not found")
            state = job.state.split()[0]
            if state == "RUNNING":
                return job
            if state not in ACTIVE:
                raise SlurmError(f"job {job_id} ended in state {job.state}")
            if time.monotonic() >= deadline:
                raise SlurmError(f"job {job_id} still {job.state} after {timeout}s")
            time.sleep(poll)


def parse_squeue_line(line: str) -> Job:
    parts = line.rstrip("\n").split("|", 5)
    parts += [""] * (6 - len(parts))
    return Job(*[p.strip() for p in parts])


def herdr_job_script(session: str, binary: str = "herdr") -> str:
    """Batch script that keeps a headless herdr server alive for the job's lifetime."""
    return (
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        'echo "orchard: herdr server on $(hostname) job=${SLURM_JOB_ID}"\n'
        f"exec {shlex.quote(binary)} --session {shlex.quote(session)} server\n"
    )
