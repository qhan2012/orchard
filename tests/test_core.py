"""Offline tests: a FakeTransport records commands and replays canned output.

These check command construction, parsing, and the ownership guard. They do
not prove behaviour against a real Slurm or herdr; see runbooks/smoke-test.md.
"""

from __future__ import annotations

import json
import shlex

import pytest

from orchardctl import inventory
from orchardctl.herdr import HerdrClient, HerdrError
from orchardctl.slurm import OwnershipError, SlurmAdapter, SlurmError, herdr_job_script
from orchardctl.transport import JobTransport, Result, SSHTransport


class FakeTransport:
    name = "fake"

    def __init__(self, replies):
        self.replies = list(replies)  # (predicate_substring, rc, stdout, stderr)
        self.calls = []

    def run(self, cmd, input=None, timeout=None):
        self.calls.append((cmd, input))
        for i, (needle, rc, out, err) in enumerate(self.replies):
            if needle in cmd:
                self.replies.pop(i)
                return Result(self.name, cmd, rc, out, err)
        raise AssertionError(f"unexpected command: {cmd}")


# -- transport ---------------------------------------------------------------
def test_ssh_argv_is_batch_mode_and_single_command():
    argv = SSHTransport("hpc1-login", ["-o", "X=1"]).argv("squeue --me")
    assert argv[:3] == ["ssh", "-o", "BatchMode=yes"]
    assert argv[-3:] == ["hpc1-login", "--", "squeue --me"]


def test_srun_wrap_quotes_inner_command():
    head = FakeTransport([("srun", 0, "ok\n", "")])
    r = JobTransport(head, "123").run("herdr agent list")
    cmd = head.calls[0][0]
    assert cmd.startswith("srun --jobid=123 --overlap")
    assert shlex.split(cmd)[-1] == "herdr agent list"
    assert r.where == "fake/job:123" and r.ok


# -- inventory ---------------------------------------------------------------
def test_inventory_merges_defaults_and_validates():
    inv = inventory.parse({
        "defaults": {"ssh_options": ["-o", "A=1"]},
        "clusters": {"c": {"head": "h", "sbatch_defaults": {"time": 60}}},
        "nodes": {"n": {"host": "box"}},
    })
    assert inv.cluster("c").ssh_options == ["-o", "A=1"]
    assert inv.cluster("c").sbatch_defaults == {"time": "60"}
    assert inv.herdr_session == "orchard"
    with pytest.raises(inventory.InventoryError):
        inventory.parse({"clusters": {"c": {"head": "h", "scheduler": "pbs"}}})
    with pytest.raises(inventory.InventoryError):
        inv.node("missing")


def test_example_inventory_parses():
    inv = inventory.load("inventory.example.yaml")
    assert "hpc1" in inv.clusters and "box1" in inv.nodes


# -- slurm -------------------------------------------------------------------
def test_submit_sends_script_on_stdin_with_tag_and_defaults():
    head = FakeTransport([("sbatch", 0, "4242;hpc1\n", "")])
    s = SlurmAdapter(head, {"partition": "gpu", "time": "01:00:00"})
    assert s.submit("#!/bin/bash\necho hi\n", "t1", time="00:10:00") == "4242"
    cmd, stdin = head.calls[0]
    args = shlex.split(cmd)
    assert args[:2] == ["sbatch", "--parsable"]
    assert "--partition=gpu" in args and "--time=00:10:00" in args
    assert "--comment=orchard:t1" in args
    assert stdin.startswith("#!/bin/bash")


def test_submit_rejects_bad_option_name():
    with pytest.raises(SlurmError):
        SlurmAdapter(FakeTransport([])).submit("x", "t", **{"x; rm -rf ~": "1"})


def test_queue_parses_comment_with_pipes():
    out = "11|job-a|RUNNING|1:02|gpu01|orchard:t1\n12|other|PENDING|0:00||user|note\n"
    s = SlurmAdapter(FakeTransport([("squeue --me", 0, out, "")]))
    a, b = s.queue()
    assert a.owned and a.nodes == "gpu01"
    assert not b.owned and b.comment == "user|note"


def test_cancel_refuses_untagged_job():
    out = "12|other|RUNNING|0:01|gpu02|\n"
    head = FakeTransport([("squeue", 0, out, "")])
    with pytest.raises(OwnershipError):
        SlurmAdapter(head).cancel("12")
    assert not any("scancel" in c for c, _ in head.calls)


def test_cancel_tagged_job():
    head = FakeTransport([("squeue", 0, "11|a|RUNNING|0:01|n|orchard:t\n", ""), ("scancel 11", 0, "", "")])
    assert SlurmAdapter(head).cancel("11").job_id == "11"


def test_cancel_job_not_in_my_queue():
    head = FakeTransport([("squeue", 1, "", "slurm_load_jobs error: Invalid job id specified")])
    with pytest.raises(OwnershipError):
        SlurmAdapter(head).cancel("99")


def test_job_falls_back_to_sacct():
    head = FakeTransport([
        ("squeue", 1, "", "Invalid job id specified"),
        ("sacct", 0, "11|a|COMPLETED|00:05:00|gpu01|orchard:t\n", ""),
    ])
    j = SlurmAdapter(head).job("11")
    assert j.state == "COMPLETED" and not j.active


def test_bad_job_id_rejected():
    with pytest.raises(SlurmError):
        SlurmAdapter(FakeTransport([])).job("11; scancel -u me")


def test_herdr_job_script_runs_server_in_foreground():
    script = herdr_job_script("orchard")
    assert script.splitlines()[-1] == "exec herdr --session orchard server"


# -- herdr -------------------------------------------------------------------
def test_herdr_command_has_session_prefix_and_parses_json():
    t = FakeTransport([("agent list", 0, json.dumps({"result": {"agents": []}}), "")])
    out = HerdrClient(t, session="orchard").agents()
    assert t.calls[0][0] == "herdr --session orchard agent list"
    assert out == {"result": {"agents": []}}


def test_herdr_prompt_quotes_text():
    t = FakeTransport([("agent prompt", 0, "{}", "")])
    HerdrClient(t).prompt("rev", "it's $HOME; rm -rf /", timeout_ms=1000)
    args = shlex.split(t.calls[0][0])
    assert args == ["herdr", "agent", "prompt", "rev", "it's $HOME; rm -rf /", "--wait", "--timeout", "1000"]


def test_herdr_error_carries_json_payload():
    t = FakeTransport([("agent wait", 1, "", json.dumps({"error": {"code": "timeout"}}))])
    with pytest.raises(HerdrError) as e:
        HerdrClient(t).wait("rev", timeout_ms=10)
    assert e.value.payload == {"error": {"code": "timeout"}}


def test_start_agent_uses_root_pane_from_workspace_create():
    ws = {"result": {"workspace": {"workspace_id": "w2"}, "root_pane": {"pane_id": "w2:p1"}}}
    t = FakeTransport([("workspace create", 0, json.dumps(ws), ""), ("agent start", 0, "{}", "")])
    out = HerdrClient(t, session="s").start_agent("rev", "claude", "~/proj")
    assert out["pane_id"] == "w2:p1"
    assert "--pane w2:p1" in t.calls[1][0]
    with pytest.raises(ValueError):
        HerdrClient(t).start_agent("Bad Name", "claude", "~")


def test_cancel_matches_exact_job_id_not_first_row():
    # A squeue that ignores --jobs must not let us cancel the wrong job.
    out = "777|a|RUNNING|0:01|n|orchard:t\n778|b|RUNNING|0:01|n|\n"
    head = FakeTransport([("squeue", 0, out, "")])
    with pytest.raises(OwnershipError):
        SlurmAdapter(head).cancel("778")
    assert not any("scancel" in c for c, _ in head.calls)


# -- connect: custom scheduler, exec, check ------------------------------------
def test_custom_scheduler_needs_job_exec_template():
    with pytest.raises(inventory.InventoryError, match="needs job_exec"):
        inventory.parse({"clusters": {"c": {"head": "j", "scheduler": "custom"}}})
    with pytest.raises(inventory.InventoryError, match="must contain"):
        inventory.parse({"clusters": {"c": {"head": "j", "scheduler": "custom", "job_exec": "x {job}"}}})
    with pytest.raises(inventory.InventoryError, match="both a cluster and a node"):
        inventory.parse({"clusters": {"x": {"head": "j"}}, "nodes": {"x": {"host": "h"}}})


def test_job_transport_uses_the_cluster_template():
    head = FakeTransport([("myrun", 0, "ok", "")])
    JobTransport(head, "a-7", "myrun --job {job} -- bash -lc {cmd}").run("echo 'hi'; ls")
    args = shlex.split(head.calls[0][0])
    assert args[:4] == ["myrun", "--job", "a-7", "--"]
    assert args[-1] == "echo 'hi'; ls"


def _cli(tmp_path, monkeypatch, fake, *argv):
    from orchardctl import cli
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        "nodes: {box1: {host: b1}}\n"
        "clusters:\n"
        "  hpc1: {head: j1}\n"
        "  corp: {head: j2, scheduler: custom, job_exec: 'myrun --job {job} -- bash -lc {cmd}'}\n"
    )
    monkeypatch.setattr(inventory.Node, "transport", lambda self: fake)
    monkeypatch.setattr(inventory.Cluster, "transport", lambda self: fake)
    return cli.run(cli.build_parser().parse_args(["--inventory", str(inv), *argv]))


def test_exec_on_node_returns_rc_and_output(tmp_path, monkeypatch):
    fake = FakeTransport([("nproc", 3, "out\n", "err\n")])
    out = _cli(tmp_path, monkeypatch, fake, "exec", "box1", "--", "nproc && false")
    assert out["rc"] == 3 and out["stdout"] == "out\n" and out["stderr"] == "err\n"
    assert fake.calls[0][0] == "nproc && false"  # one argument = shell string


def test_exec_argv_words_are_quoted(tmp_path, monkeypatch):
    fake = FakeTransport([("ls", 0, "", "")])
    _cli(tmp_path, monkeypatch, fake, "exec", "box1", "--", "ls", "my dir")
    assert fake.calls[0][0] == "ls 'my dir'"


def test_exec_in_custom_scheduler_job(tmp_path, monkeypatch):
    fake = FakeTransport([("myrun", 0, "gpu07\n", "")])
    out = _cli(tmp_path, monkeypatch, fake, "exec", "corp", "--job", "j-42", "--", "hostname")
    assert out["stdout"] == "gpu07\n" and out["where"] == "fake/job:j-42"
    assert shlex.split(fake.calls[0][0])[:3] == ["myrun", "--job", "j-42"]


def test_exec_on_cluster_without_job_runs_on_jumper(tmp_path, monkeypatch):
    fake = FakeTransport([("hostname", 0, "jumper\n", "")])
    out = _cli(tmp_path, monkeypatch, fake, "exec", "corp", "--", "hostname")
    assert out["where"] == "fake" and fake.calls[0][0] == "hostname"


def test_exec_job_on_a_node_is_rejected(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="needs a cluster"):
        _cli(tmp_path, monkeypatch, FakeTransport([]), "exec", "box1", "--job", "1", "--", "true")


def test_check_parses_probe_output(tmp_path, monkeypatch):
    probe = "host=gpu07\ngpu=card0,5,10\ngpu=card1,0,3\nherdr=missing\nagent_claude=/usr/bin/claude\n"
    fake = FakeTransport([("hostname", 0, probe, "")])
    out = _cli(tmp_path, monkeypatch, fake, "check", "box1")
    assert out["reachable"] and out["host"] == "gpu07" and out["herdr"] == "missing"
    assert out["gpu"] == ["card0,5,10", "card1,0,3"]


def test_check_unreachable_reports_stderr(tmp_path, monkeypatch):
    fake = FakeTransport([("hostname", 255, "", "ssh: Could not resolve hostname b1")])
    out = _cli(tmp_path, monkeypatch, fake, "check", "box1")
    assert not out["reachable"] and out["rc"] == 255 and "resolve" in out["stderr"]


def test_slurm_commands_refused_on_custom_scheduler(tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="custom"):
        _cli(tmp_path, monkeypatch, FakeTransport([]), "slurm", "corp", "queue")
