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
from orchardctl.transport import Result, SrunTransport, SSHTransport


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
    r = SrunTransport(head, "123").run("herdr agent list")
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
