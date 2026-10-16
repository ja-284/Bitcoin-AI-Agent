"""tools/gate.py: the quality gate fails safely. Fake runners and a fake git only; nothing is committed or pushed."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("gate", Path("tools/gate.py"))
gate = importlib.util.module_from_spec(_spec)
sys.modules["gate"] = gate
_spec.loader.exec_module(gate)


def _runner(codes: dict[str, int], calls: list):
    def run(cmd, cwd=None, env=None):
        calls.append(cmd[-1])
        return subprocess.CompletedProcess(cmd, codes[cmd[-1]])
    return run


def _steps(*names):
    return [gate.Step(n, ["python", n]) for n in names]


def test_the_first_failure_stops_the_gate_and_later_steps_are_not_run():
    calls = []
    rep = gate.run_steps(_steps("a", "b", "c"), run=_runner({"a": 0, "b": 1, "c": 0}, calls))
    assert calls == ["a", "b"], "a step after a failure must not run"
    assert [(r.status, r.code) for r in rep.results] == [("PASSED", 0), ("FAILED", 1), ("NOT RUN", None)]
    assert rep.ok is False and "RESULT: FAILED" in rep.text() and "PASSED (every" not in rep.text()


def test_the_gate_passes_only_when_every_step_ran_and_returned_0():
    rep = gate.run_steps(_steps("a", "b"), run=_runner({"a": 0, "b": 0}, []))
    assert rep.ok is True and "RESULT: PASSED" in rep.text()
    assert gate.Report([]).ok is False, "an empty gate must never count as passed"


def test_a_step_that_cannot_even_start_is_a_failure():
    def broken(cmd, cwd=None, env=None):
        raise FileNotFoundError("no such interpreter")
    rep = gate.run_steps(_steps("a", "b"), run=broken)
    assert rep.results[0].status == "FAILED" and rep.results[1].status == "NOT RUN" and not rep.ok


def test_main_check_returns_the_gates_real_exit_code(monkeypatch):
    monkeypatch.setattr(gate, "steps", lambda *a: _steps("a"))
    monkeypatch.setattr(gate, "run_steps", lambda todo: gate.Report([gate.Result("a", "FAILED", 3)]))
    assert gate.main(["check"]) == 1
    monkeypatch.setattr(gate, "run_steps", lambda todo: gate.Report([gate.Result("a", "PASSED", 0)]))
    assert gate.main(["check"]) == 0


class FakeGit:
    def __init__(self, porcelain="", push_code=0, upstream_matches=True):
        self.calls, self.porcelain, self.push_code, self.upstream_matches = [], porcelain, push_code, upstream_matches
        self.staged = False

    def __call__(self, *args):
        self.calls.append(args)
        out, code = "", 0
        if args[0] == "status":
            out = self.porcelain.replace(" M ", "M  ") if self.staged else self.porcelain
        elif args[0] == "add":
            self.staged = True
        elif args[0] == "push":
            code = self.push_code
        elif args[:2] == ("rev-parse", "HEAD"):
            out = "abc1234"
        elif args[:2] == ("rev-parse", "@{u}"):
            out = "abc1234" if self.upstream_matches else "0000000"
        elif args[0] == "rev-list":
            out = "1"
        return subprocess.CompletedProcess(args, code, out, "")

    def did(self, verb):
        return any(c[0] == verb for c in self.calls)


PASS = gate.Report([gate.Result("unit", "PASSED", 0)])
FAIL = gate.Report([gate.Result("unit", "FAILED", 1)])


def test_ship_never_commits_or_pushes_after_a_failed_gate(tmp_path):
    msg = tmp_path / "m.txt"
    msg.write_text("x")
    g = FakeGit(" M agent/x.py\n")
    assert gate.ship(str(msg), ["agent/x.py"], [], git=g, run_gate=lambda todo: FAIL) == 1
    assert not g.did("commit") and not g.did("push")


def test_ship_refuses_when_other_changes_would_make_the_tested_tree_differ(tmp_path):
    msg = tmp_path / "m.txt"
    msg.write_text("x")
    g = FakeGit(" M agent/x.py\n?? notes.txt\n")
    ran = []
    assert gate.ship(str(msg), ["agent/x.py"], [], git=g, run_gate=lambda todo: ran.append(1) or PASS) == 2
    assert not ran and not g.did("add") and not g.did("commit")


def test_ship_commits_and_pushes_after_a_passed_gate(tmp_path):
    msg = tmp_path / "m.txt"
    msg.write_text("x")
    g = FakeGit(" M agent/x.py\n")
    assert gate.ship(str(msg), ["agent"], [], git=g, run_gate=lambda todo: PASS) == 0
    assert g.did("commit") and g.did("push")


def test_push_never_pushes_after_a_failed_gate():
    g = FakeGit("")
    assert gate.push([], git=g, run_gate=lambda todo: FAIL) == 1 and not g.did("push")


def test_push_refuses_a_dirty_tree():
    g = FakeGit(" M agent/x.py\n")
    assert gate.push([], git=g, run_gate=lambda todo: PASS) == 2 and not g.did("push")


@pytest.mark.parametrize("push_code,matches", [(1, True), (0, False)])
def test_a_push_that_failed_or_did_not_land_is_reported_as_failed(push_code, matches):
    g = FakeGit("", push_code=push_code, upstream_matches=matches)
    assert gate.push([], git=g, run_gate=lambda todo: PASS) == 1


def test_the_unit_step_runs_as_ci_does_with_no_database_reachable():
    s = gate.steps()[0]
    assert s.env["DATABASE_URL"] == gate.UNREACHABLE_DB and s.env["BITCOIN_AGENT_DB_TESTS"] is None
    assert [x.name for x in gate.steps(integration=True, all_mutations=True)][1:] == [
        "integration tests (real Postgres, scratch schema)", "mutation guards (all)"]


def test_ship_no_push_commits_but_does_not_push(tmp_path):
    msg = tmp_path / "m.txt"
    msg.write_text("x")
    g = FakeGit(" M agent/x.py\n")
    assert gate.ship(str(msg), ["agent/x.py"], [], git=g, run_gate=lambda todo: PASS, push_too=False) == 0
    assert g.did("commit") and not g.did("push")
