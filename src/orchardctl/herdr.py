"""Remote herdr control through a Transport.

Built against herdr v0.9.5 CLI (docs/next/website/.../cli-reference.mdx,
skills/herdr/SKILL.md in github.com/ogulcancelik/herdr). The installed
binary is the authority: check `herdr --help` on the target if a command fails.

Facts this module relies on:
- `--session <name>` selects a named, independent server.
- `herdr server` runs the headless server in the foreground.
- control commands print JSON on stdout; on timeout or server error they
  print a JSON error on stderr and exit 1; usage errors exit 2.
- a timeout does NOT prove a prompt was not delivered: read before retrying.
"""

from __future__ import annotations

import json
import re
import shlex
from typing import Any

from .transport import Result, Transport

_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
SOURCES = {"visible", "recent", "recent-unwrapped", "detection"}


class HerdrError(RuntimeError):
    def __init__(self, result: Result, payload: Any = None):
        self.result = result
        self.payload = payload
        msg = payload if payload is not None else result.stderr.strip()
        super().__init__(f"[{result.where}] herdr exit {result.returncode}: {msg}")


class HerdrClient:
    def __init__(self, transport: Transport, session: str | None = None, binary: str = "herdr"):
        self.t = transport
        self.session = session
        self.binary = binary

    # -- plumbing ---------------------------------------------------------
    def cmd(self, *args: str) -> str:
        parts = [self.binary]
        if self.session:
            parts += ["--session", self.session]
        parts += list(args)
        return " ".join(shlex.quote(p) for p in parts)

    def call(self, *args: str, timeout: float | None = None) -> Any:
        r = self.t.run(self.cmd(*args), timeout=timeout)
        if not r.ok:
            raise HerdrError(r, _maybe_json(r.stderr))
        out = _maybe_json(r.stdout)
        return out if out is not None else r.stdout

    # -- server -----------------------------------------------------------
    def version(self) -> str:
        r = self.t.run(f"{shlex.quote(self.binary)} --version")
        if not r.ok:
            raise HerdrError(r)
        return r.stdout.strip()

    def server_status(self) -> Any:
        return self.call("status", "server")

    def start_server(self, log_dir: str = "~/.orchard") -> str:
        """Start a detached headless server on a plain SSH node.

        On Slurm, use slurm.herdr_job_script instead: the job owns the server.
        """
        log = f"{log_dir}/herdr-{self.session or 'default'}.log"
        cmd = (
            f"mkdir -p {log_dir} && "
            f"setsid nohup {self.cmd('server')} > {log} 2>&1 < /dev/null & echo started"
        )
        r = self.t.run(cmd)
        if not r.ok:
            raise HerdrError(r)
        return log

    def stop_server(self) -> Any:
        return self.call("server", "stop")

    # -- topology ---------------------------------------------------------
    def workspaces(self) -> Any:
        return self.call("workspace", "list")

    def create_workspace(self, cwd: str, label: str | None = None) -> Any:
        args = ["workspace", "create", "--cwd", cwd, "--no-focus"]
        if label:
            args += ["--label", label]
        return self.call(*args)

    # -- agents -----------------------------------------------------------
    def agents(self) -> Any:
        return self.call("agent", "list")

    def agent(self, target: str) -> Any:
        return self.call("agent", "get", target)

    def start_agent(self, name: str, kind: str, cwd: str, timeout_ms: int = 30000,
                    agent_args: list[str] | None = None) -> dict:
        """Create a workspace at cwd and start a named agent in its root pane."""
        if not _NAME.match(name):
            raise ValueError(f"agent name must match {_NAME.pattern}: {name!r}")
        ws = self.create_workspace(cwd, label=name)
        pane = _dig(ws, "result", "root_pane", "pane_id")
        if not pane:
            raise RuntimeError(f"workspace create returned no root pane: {ws!r}")
        args = ["agent", "start", name, "--kind", kind, "--pane", pane, "--timeout", str(timeout_ms)]
        if agent_args:
            args += ["--", *agent_args]
        started = self.call(*args)
        return {"pane_id": pane, "workspace": ws, "start": started}

    def prompt(self, target: str, text: str, wait: bool = True, timeout_ms: int | None = None) -> Any:
        args = ["agent", "prompt", target, text]
        if wait:
            args.append("--wait")
        if timeout_ms is not None:
            args += ["--timeout", str(timeout_ms)]
        return self.call(*args)

    def wait(self, target: str, until: list[str] | None = None, timeout_ms: int | None = None) -> Any:
        args = ["agent", "wait", target]
        for u in until or []:
            args += ["--until", u]
        if timeout_ms is not None:
            args += ["--timeout", str(timeout_ms)]
        return self.call(*args)

    def read(self, target: str, lines: int = 120, source: str = "recent-unwrapped") -> str:
        if source not in SOURCES:
            raise ValueError(f"source must be one of {sorted(SOURCES)}")
        out = self.call("agent", "read", target, "--source", source, "--lines", str(lines))
        return out if isinstance(out, str) else json.dumps(out, indent=2)

    def send_keys(self, target: str, *keys: str) -> Any:
        return self.call("agent", "send-keys", target, *keys)


def _maybe_json(text: str) -> Any:
    text = text.strip()
    if not text or text[0] not in "{[":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _dig(obj: Any, *keys: str) -> Any:
    for k in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return obj
