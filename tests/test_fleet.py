"""Offline tests for the fleet loop: ledger, board, watch events, review, budget, cleanup.

A FakeHerdr per target replays canned `agent list` / `agent get` replies and
records every herdr command, so the tests check what orchard would run.
"""

from __future__ import annotations

import json
import shlex

import pytest

from orchardctl import cli, fleet as fl
from orchardctl.herdr import HerdrClient
from orchardctl.ledger import Ledger, fold, job_key, node_key
from orchardctl.transport import Result


def agent(name, status, kind="claude", seq=1, cwd="/w/proj"):
    return {"name": name, "agent": kind, "agent_status": status, "pane_id": f"w1:p{seq}",
            "cwd": cwd, "state_change_seq": seq, "workspace_id": "w1", "tab_id": "w1:t1",
            "terminal_id": "t", "focused": False}


def listing(*agents):
    return json.dumps({"id": "1", "result": {"type": "agent_list", "agents": list(agents)}})


class FakeHerdr:
    """Transport stand-in for one herdr target. Routes by herdr subcommand."""

    name = "fake"

    def __init__(self, agents=(), fail=None):
        self.agents = list(agents)
        self.fail = fail
        self.calls: list[str] = []

    def run(self, cmd, input=None, timeout=None):
        self.calls.append(cmd)
        if "setsid nohup" in cmd:
            return Result(self.name, cmd, 0, "started\n", "")
        if self.fail:
            return Result(self.name, cmd, 255, "", self.fail)
        args = shlex.split(cmd)
        sub = args[args.index("--session") + 2:] if "--session" in args else args[1:]
        if sub[:2] == ["agent", "list"]:
            return Result(self.name, cmd, 0, listing(*self.agents), "")
        if sub[:2] == ["agent", "get"]:
            a = next(x for x in self.agents if x["name"] == sub[2])
            return Result(self.name, cmd, 0, json.dumps({"result": {"type": "agent_info", "agent": a}}), "")
        if sub[:2] == ["workspace", "create"]:
            return Result(self.name, cmd, 0, json.dumps({"result": {"root_pane": {"pane_id": "w9:p1"}}}), "")
        if sub[:2] == ["agent", "start"]:
            self.agents.append(agent(sub[2], "idle", kind=sub[sub.index("--kind") + 1], seq=9))
            return Result(self.name, cmd, 0, "{}", "")
        if sub[:2] in (["agent", "prompt"], ["agent", "read"], ["server", "stop"]):
            return Result(self.name, cmd, 0, "screen text\n" if sub[1] == "read" else "{}", "")
        raise AssertionError(f"unexpected herdr command: {cmd}")


@pytest.fixture
def env(tmp_path, monkeypatch):
    inv = tmp_path / "inventory.yaml"
    inv.write_text(
        "clusters: {hpc1: {head: h}}\n"
        "nodes: {box1: {host: b1}, box2: {host: b2}}\n"
        "fleet: {max_agents: 3, roles: {reviewer: codex}}\n"
    )
    fakes: dict[str, FakeHerdr] = {}

    def client(self, t, session=None):
        f = fakes.setdefault(t.key, FakeHerdr())
        return HerdrClient(f, session=session or "orchard")

    monkeypatch.setattr(cli.Ctx, "client", client)

    def run(*argv):
        a = cli.build_parser().parse_args(["--inventory", str(inv), "--state", str(tmp_path / "state"), *argv])
        return cli.run(a)

    return {"run": run, "fakes": fakes, "ledger": Ledger(tmp_path / "state" / "ledger.jsonl"),
            "tmp": tmp_path}


# -- ledger ---------------------------------------------------------------------
def test_ledger_fold_tracks_open_close_and_agents(tmp_path):
    lg = Ledger(tmp_path / "l.jsonl")
    lg.record("job_launched", job_key("c", "1"), session="s", run="alpha")
    lg.record("agent_started", job_key("c", "1"), name="b", kind="claude", role="builder")
    lg.record("server_up", node_key("box"), session="s")
    lg.record("server_down", node_key("box"))
    t = lg.targets()
    assert t["job:c/1"].open and t["job:c/1"].run == "alpha"
    assert t["job:c/1"].agents["b"]["kind"] == "claude"
    assert not t["node:box"].open
    assert [r.key for r in lg.open_targets()] == ["job:c/1"]


def test_agent_on_foreign_server_is_not_owned():
    t = fold([{"ts": "x", "event": "agent_started", "target": "node:n", "name": "a"}])
    assert t["node:n"].open and not t["node:n"].owned


# -- board ------------------------------------------------------------------------
def test_snapshot_sorts_by_attention_and_survives_bad_target():
    fakes = {
        "node:a": FakeHerdr([agent("w", "working"), agent("d", "done", seq=2)]),
        "node:b": FakeHerdr([agent("blk", "blocked", seq=3), agent("i", "idle", seq=4)]),
        "node:c": FakeHerdr(fail="ssh: connect to host c: No route to host"),
    }
    targets = [(fl.Target.parse(k), None) for k in fakes]
    snap = fl.snapshot(targets, lambda t, s: HerdrClient(fakes[t.key]))
    assert [r["name"] for r in snap["agents"]] == ["blk", "d", "i", "w"]
    assert snap["needs_you"] == 2 and snap["live_agents"] == 4
    bad = [t for t in snap["targets"] if not t["ok"]]
    assert bad[0]["target"] == "node:c" and "No route" in bad[0]["error"]


def test_target_parse_round_trip():
    assert fl.Target.parse("job:hpc1/123").key == "job:hpc1/123"
    assert fl.Target.parse("node:box1").node == "box1"
    with pytest.raises(ValueError):
        fl.Target.parse("hpc1/123")


# -- watch ------------------------------------------------------------------------
def snap_of(*rows, bad=()):
    return {"agents": [fl.row(t, a) for t, a in rows],
            "targets": [{"target": b, "ok": False, "error": "down"} for b in bad]}


def test_diff_fires_once_per_state_change():
    s1 = snap_of(("node:a", agent("x", "working", seq=1)))
    s2 = snap_of(("node:a", agent("x", "done", seq=2)))
    s3 = snap_of(("node:a", agent("x", "done", seq=2)))  # nobody looked yet: no repeat
    s4 = snap_of(("node:a", agent("x", "blocked", seq=3)))
    assert fl.diff(None, s1) == []
    assert [e["event"] for e in fl.diff(s1, s2)] == ["finished"]
    assert fl.diff(s2, s3) == []
    assert [e["event"] for e in fl.diff(s3, s4)] == ["needs_decision"]


def test_diff_reports_gone_agent_and_unreachable_target_once():
    s1 = snap_of(("node:a", agent("x", "working")), ("node:b", agent("y", "working")))
    s2 = snap_of(("node:a", agent("x", "working")), bad=["node:b"])
    ev = fl.diff(s1, s2)
    # y vanished because node:b is down: report the target, not a false "agent gone".
    assert [e["event"] for e in ev] == ["target_unreachable"]
    assert fl.diff(s2, s2) == []
    s3 = snap_of()
    assert [e["event"] for e in fl.diff(s2, s3)] == ["agent_gone"]


def test_notify_formats_argv_without_shell_and_never_raises():
    ev = {"event": "needs_decision", "target": "node:a", "name": "x", "status": "blocked"}
    assert fl.notify(["true", "{title}", "{body}"], ev) == {"notify_rc": 0}
    out = fl.notify(["/no/such/notifier", "{title}"], ev)
    assert out["notify_rc"] is None and "notify_err" in out
    assert fl.notify([], ev) is None


# -- CLI flows ----------------------------------------------------------------------
def test_up_start_fleet_and_down_use_the_ledger(env):
    run = env["run"]
    # `herdr up` starts a detached server through a shell; the ledger entry is what matters here.
    env["ledger"].record("server_up", "node:box1", session="orchard", run="alpha")
    out = run("herdr", "--node", "box1", "start", "bld", "--kind", "claude", "--cwd", "/w/proj", "--run", "alpha")
    assert out["target"] == "node:box1" and out["budget"] == {"live_agents": 0, "budget": 3}
    board = run("fleet")
    assert board["agents"][0]["name"] == "bld" and board["agents"][0]["role"] == "builder"
    assert board["agents"][0]["run"] == "alpha"
    run("herdr", "--node", "box1", "down")
    assert not env["ledger"].targets()["node:box1"].open


def test_down_refuses_server_orchard_did_not_start(env):
    with pytest.raises(cli.OwnershipError):
        env["run"]("herdr", "--node", "box2", "down")
    assert not any("server stop" in c for c in env["fakes"].get("node:box2", FakeHerdr()).calls)


def test_start_refuses_past_the_attention_budget(env):
    env["ledger"].record("server_up", "node:box1")
    env["fakes"]["node:box1"] = FakeHerdr([agent("a", "working", seq=1), agent("b", "working", seq=2),
                                          agent("c", "done", seq=3)])
    with pytest.raises(cli.BudgetError):
        env["run"]("herdr", "--node", "box1", "start", "d", "--kind", "claude", "--cwd", "/w")
    assert not any("agent start" in c for c in env["fakes"]["node:box1"].calls)
    out = env["run"]("herdr", "--node", "box1", "start", "d", "--kind", "claude", "--cwd", "/w", "--over-budget")
    assert out["budget"] is None


def test_review_uses_a_different_model_in_the_builders_cwd(env):
    env["ledger"].record("server_up", "node:box1")
    env["fakes"]["node:box1"] = FakeHerdr([agent("bld", "done", kind="claude", cwd="/w/proj")])
    out = env["run"]("herdr", "--node", "box1", "review", "bld", "--base", "origin/main", "--timeout-ms", "1000")
    assert out["reviewer"] == "bld-rev" and out["kind"] == "codex" and out["cwd"] == "/w/proj"
    calls = env["fakes"]["node:box1"].calls
    ws = next(shlex.split(c) for c in calls if "workspace create" in c)
    assert ws[ws.index("--cwd") + 1] == "/w/proj"
    prompt = next(shlex.split(c) for c in calls if "agent prompt" in c)
    text = prompt[prompt.index("prompt") + 2]
    assert "Do not edit" in text and "git diff origin/main...HEAD" in text and "VERDICT" in text
    rec = env["ledger"].agent("node:box1", "bld-rev")
    assert rec["role"] == "reviewer" and rec["of"] == "bld"


def test_review_refuses_same_kind_as_builder(env):
    env["ledger"].record("server_up", "node:box1")
    env["fakes"]["node:box1"] = FakeHerdr([agent("bld", "done", kind="codex")])
    with pytest.raises(ValueError, match="same as the builder"):
        env["run"]("herdr", "--node", "box1", "review", "bld")
    assert not any("agent start" in c for c in env["fakes"]["node:box1"].calls)


def test_watch_once_prints_events_and_logs_them(env, capsys):
    env["ledger"].record("server_up", "node:box1")
    env["fakes"]["node:box1"] = FakeHerdr([agent("bld", "blocked"), agent("w", "working", seq=2)])
    assert env["run"]("watch", "--once", "--no-notify") is cli.STREAMED
    lines = [json.loads(l) for l in capsys.readouterr().out.splitlines()]
    assert [(e["event"], e["name"]) for e in lines] == [("needs_decision", "bld")]
    assert (env["tmp"] / "state" / "events.jsonl").read_text().count("needs_decision") == 1
    # A second cron-style run sees no change, so it reports nothing.
    env["run"]("watch", "--once", "--no-notify")
    assert capsys.readouterr().out == ""
    env["run"]("watch", "--once", "--no-notify", "--fresh")
    assert "needs_decision" in capsys.readouterr().out


def test_digest_writes_markdown_with_screens_of_agents_that_need_you(env):
    env["ledger"].record("server_up", "node:box1")
    env["fakes"]["node:box1"] = FakeHerdr([agent("bld", "done"), agent("w", "working", seq=2)])
    out = env["run"]("digest", "--out", str(env["tmp"] / "d.md"))
    md = (env["tmp"] / "d.md").read_text()
    assert out["needs_you"] == 1
    assert "**1 need you**" in md and "### bld @ `node:box1`" in md and "screen text" in md
    assert "### w @" not in md  # working agents are not interrupted, not read


def test_cleanup_is_dry_run_by_default_and_only_touches_owned_targets(env):
    env["ledger"].record("server_up", "node:box1", run="alpha")
    env["ledger"].record("agent_started", "node:box2", name="x")  # foreign server
    plan = env["run"]("cleanup")
    actions = {s["target"]: s["action"] for s in plan["steps"]}
    assert plan["dry_run"] and actions["node:box1"] == "herdr server stop"
    assert actions["node:box2"].startswith("forget")
    assert not any("server stop" in c for f in env["fakes"].values() for c in f.calls)
    done = env["run"]("cleanup", "--yes")
    assert all(s["done"] for s in done["steps"])
    assert not env["ledger"].targets()["node:box1"].open
    assert not env["ledger"].targets()["node:box2"].open
    # The foreign server on box2 was never asked to stop.
    assert not any("server stop" in c for c in env["fakes"].get("node:box2", FakeHerdr()).calls)


def test_up_records_server_in_ledger(env):
    out = env["run"]("herdr", "--node", "box1", "up", "--run", "alpha")
    assert out["target"] == "node:box1"
    rec = env["ledger"].targets()["node:box1"]
    assert rec.open and rec.owned and rec.run == "alpha"


def test_launch_and_cancel_record_the_job(env, monkeypatch):
    from orchardctl import inventory
    from test_core import FakeTransport

    head = FakeTransport([
        ("sbatch", 0, "555\n", ""),
        ("squeue", 0, "555|orchard-orchard|RUNNING|0:01|gpu1|orchard:herdr-x\n", ""),
        ("scancel 555", 0, "", ""),
    ])
    monkeypatch.setattr(inventory.Cluster, "transport", lambda self: head)
    out = env["run"]("slurm", "hpc1", "launch-herdr", "--run", "beta", "--tag", "herdr-x")
    assert out["target"] == "job:hpc1/555"
    assert env["ledger"].targets()["job:hpc1/555"].run == "beta"
    env["run"]("slurm", "hpc1", "cancel", "555")
    assert not env["ledger"].targets()["job:hpc1/555"].open
