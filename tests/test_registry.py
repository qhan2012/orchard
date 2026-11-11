"""Registry unit tests and CLI flow tests. SSH is replaced by a fake."""

from __future__ import annotations

import json

import pytest

from orchardctl import cli
from orchardctl.registry import ORCHARD, USER, Registry, RegistryError
from orchardctl.transport import Result, SSHTransport


# -- unit ---------------------------------------------------------------------
def test_record_persist_end_forget(tmp_path):
    reg = Registry(tmp_path)
    e = reg.record(ORCHARD, "orchard", cluster="hpc1", job_id="7", tag="t")
    assert e.id == "job:hpc1/7/orchard" and e.created_at
    assert Registry(tmp_path).get(e.id).tag == "t"  # survives a new process
    assert reg.end_job("hpc1", "7") == [e.id]
    assert reg.list() == [] and len(reg.list(include_ended=True)) == 1
    reg.forget(e.id)
    assert reg.get(e.id) is None
    with pytest.raises(RegistryError):
        reg.forget(e.id)


def test_owner_conflict_and_require_orchard(tmp_path):
    reg = Registry(tmp_path)
    u = reg.record(USER, "orchard", node="box1", note="my run")
    with pytest.raises(RegistryError):
        reg.record(ORCHARD, "orchard", node="box1")
    with pytest.raises(RegistryError):
        reg.require_orchard(u.id)
    with pytest.raises(RegistryError):
        reg.require_orchard("node:other/orchard")
    # same owner again: keeps the first record
    assert reg.record(USER, "orchard", node="box1").created_at == u.created_at
    assert reg.get(u.id).note == "my run"
    # an ended record no longer blocks a new owner
    reg.end(u.id)
    assert reg.record(ORCHARD, "orchard", node="box1").started_by == ORCHARD


# -- CLI flows ------------------------------------------------------------------
@pytest.fixture
def env(tmp_path, monkeypatch):
    (tmp_path / "inventory.yaml").write_text(
        "clusters: {hpc1: {head: h}}\nnodes: {box1: {host: b}}\n"
    )
    monkeypatch.setenv("ORCHARD_INVENTORY", str(tmp_path / "inventory.yaml"))
    monkeypatch.delenv("ORCHARD_STATE_DIR", raising=False)
    calls = []

    def fake_run(self, cmd, input=None, timeout=None):
        calls.append(cmd)
        out = ""
        if cmd.startswith("sbatch"):
            out = "900\n"
        elif cmd.startswith("squeue"):
            out = "900|orchard-orchard|RUNNING|0:01|gpu01|orchard:x\n"
        elif "server stop" in cmd:
            out = "{}"
        return Result(self.name, cmd, 0, out, "")

    monkeypatch.setattr(SSHTransport, "run", fake_run)
    return tmp_path, calls


def run(capsys, *argv):
    rc = cli.main(list(argv))
    cap = capsys.readouterr()
    return rc, (json.loads(cap.out) if rc == 0 else json.loads(cap.err))


def test_launch_records_and_cancel_ends(env, capsys):
    tmp, _ = env
    rc, out = run(capsys, "slurm", "hpc1", "launch-herdr")
    assert rc == 0 and out["registry_id"] == "job:hpc1/900/orchard"
    assert (tmp / "state" / "sessions.json").is_file()
    rc, out = run(capsys, "session", "list")
    assert [s["started_by"] for s in out["sessions"]] == ["orchard"]
    rc, out = run(capsys, "slurm", "hpc1", "cancel", "900")
    assert rc == 0 and out["sessions_ended"] == ["job:hpc1/900/orchard"]
    assert run(capsys, "session", "list")[1]["sessions"] == []
    assert len(run(capsys, "session", "list", "--all")[1]["sessions"]) == 1


def test_down_refuses_user_session_until_forced(env, capsys):
    _, calls = env
    rc, out = run(capsys, "session", "adopt", "--node", "box1", "--note", "manual")
    assert rc == 0 and out["started_by"] == "user"
    rc, err = run(capsys, "herdr", "--node", "box1", "down")
    assert rc == 1 and err["error"] == "RegistryError"
    rc, err = run(capsys, "herdr", "--node", "box1", "up")
    assert rc == 1 and err["error"] == "RegistryError"
    assert calls == []  # no remote command ran
    rc, out = run(capsys, "herdr", "--node", "box1", "down", "--force")
    assert rc == 0 and any("server stop" in c for c in calls)


def test_down_refuses_unregistered_session(env, capsys):
    _, calls = env
    rc, err = run(capsys, "herdr", "--node", "box1", "down")
    assert rc == 1 and "not in the registry" in err["message"] and calls == []


def test_up_then_down(env, capsys):
    _, calls = env
    rc, out = run(capsys, "herdr", "--node", "box1", "up")
    assert rc == 0 and out["registry_id"] == "node:box1/orchard"
    rc, out = run(capsys, "herdr", "--node", "box1", "down")
    assert rc == 0 and out["stopped"] == "node:box1/orchard"
    assert run(capsys, "session", "list")[1]["sessions"] == []


def test_adopt_checks_inventory(env, capsys):
    rc, err = run(capsys, "session", "adopt", "--node", "nope")
    assert rc == 1 and err["error"] == "InventoryError"
