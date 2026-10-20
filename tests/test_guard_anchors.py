"""
Every mutation guard must still find the code it breaks (tools/guard_mutations.py).

A guard whose target text is gone breaks nothing, so it tests nothing; one whose text occurs twice is ambiguous. On
2026-10-17 a rewrite of load_bars (59aa794) left one guard pointing at code that no longer existed. Nothing noticed
for three days: the full mutation run takes about two hours, and the gate's subset runs check only their own guards
(F1, weekly audit 2026-10-20). This check takes a fraction of a second, so it runs with the unit tests on every
commit (tools/gate.py) and in CI. The mutation runner leaves this file out of its own runs (ANCHOR_TEST there).
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("guard_mutations", Path("tools/guard_mutations.py"))
gm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gm)


def test_every_registered_guard_and_the_control_find_their_target_exactly_once():
    stale = gm.stale_anchors(gm.MUTATIONS + [gm.NULL_MUTATION])
    assert not stale, "obsolete or ambiguous mutation targets:\n" + "\n".join(
        f"  {m.file}: {n} matches: {m.what}" for m, n in stale)


def test_an_obsolete_ambiguous_or_missing_target_is_reported_and_a_valid_one_is_not(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_bytes(b"x = 1\nif a > b:\n    pass\nif a > b:\n    pass\n")
    valid = gm.Mutation("t", "pkg/mod.py", "x = 1", "x = 2", "valid")
    obsolete = gm.Mutation("t", "pkg/mod.py", "y = 1", "y = 2", "obsolete")
    ambiguous = gm.Mutation("t", "pkg/mod.py", "if a > b:", "if False:", "ambiguous")
    missing = gm.Mutation("t", "pkg/absent.py", "x = 1", "x = 2", "file missing")
    assert gm.stale_anchors([valid], root=tmp_path) == []
    found = gm.stale_anchors([valid, obsolete, ambiguous, missing], root=tmp_path)
    assert [(m.what, n) for m, n in found] == [("obsolete", 0), ("ambiguous", 2), ("file missing", 0)]


def test_the_runner_refuses_before_running_anything_and_names_every_stale_guard(tmp_path, monkeypatch, capsys):
    (tmp_path / "mod.py").write_bytes(b"x = 1\n")
    monkeypatch.setattr(gm, "ROOT", tmp_path)
    monkeypatch.setattr(gm, "MUTATIONS", [gm.Mutation("t", "mod.py", "gone = 1", "gone = 2", "first stale"),
                                          gm.Mutation("t", "mod.py", "also gone", "x", "second stale")])
    monkeypatch.setattr(gm, "NULL_MUTATION", gm.Mutation("control", "mod.py", "x = 1", "x = 1  # c", "control"))
    monkeypatch.setattr(gm.subprocess, "run", lambda *a, **k: type("P", (), {"stdout": ""})())  # a clean `git status`
    monkeypatch.setattr(gm, "run_suite", lambda: pytest.fail("the suite ran although a guard was stale"))
    monkeypatch.setattr(sys, "argv", ["guard_mutations.py"])
    assert gm.main() == 2
    out = capsys.readouterr().out
    assert "first stale" in out and "second stale" in out
    assert (tmp_path / "mod.py").read_bytes() == b"x = 1\n"


def test_mutation_runs_leave_the_anchor_check_out(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return type("P", (), {"returncode": 0, "stdout": "1 passed"})()

    monkeypatch.setattr(gm.subprocess, "run", fake_run)
    gm.run_suite()
    assert f"--ignore={Path(__file__).resolve().relative_to(gm.ROOT).as_posix()}" in seen["cmd"]
