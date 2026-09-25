"""
The live move-size shadow record (agent/shadow) must stay separate from the live BUY/HOLD/SELL signal
-- in both directions. Until 2026-09-25 this held by construction only; these tests make it a guard.

  1. Nothing on the live signal's path may import the shadow package: the shadow model can never feed
     the decision, its scores or its confidence.
  2. The shadow package may READ the live record (one cross-check of the reference close) but never
     write to it: no INSERT / UPDATE / DELETE / TRUNCATE on predictions or prediction_outcomes.
"""

import ast
import re
from pathlib import Path

LIVE_PATH = ["agent/orchestrator.py", "run.py", *map(str, Path("agent/scoring").glob("*.py")),
             *map(str, Path("agent/decision").glob("*.py")), *map(str, Path("agent/ai").glob("*.py")),
             *map(str, Path("agent/indicators").glob("*.py")), *map(str, Path("agent/patterns").glob("*.py")),
             *map(str, Path("agent/news").glob("*.py")), *map(str, Path("agent/data_providers").glob("*.py"))]
SHADOW = sorted(Path("agent/shadow").glob("*.py"))
LIVE_TABLES = ("predictions", "prediction_outcomes")


def _imports(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module)
            out |= {f"{n.module}.{a.name}" for a in n.names}
        elif isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
    return out


def _writes_to_live_tables(source: str) -> list[str]:
    """SQL in string constants that writes to a live table (comments and docstrings are not SQL)."""
    tree = ast.parse(source)
    docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                  if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
                  and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    hits = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings:
            sql = " ".join(n.value.split()).upper()
            for t in LIVE_TABLES:
                if re.search(rf"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE(\s+TABLE)?)\s+{t.upper()}\b", sql):
                    hits.append(n.value.strip()[:80])
    return hits


def test_the_live_signal_path_never_imports_the_shadow_model():
    assert len(LIVE_PATH) > 15, "the live-path file list is suspiciously short"
    offenders = {p: sorted(i for i in _imports(p) if i.startswith("agent.shadow")) for p in LIVE_PATH}
    assert not {p: i for p, i in offenders.items() if i}, offenders


def test_the_shadow_package_never_writes_to_the_live_record():
    assert SHADOW, "no shadow modules found"
    for path in SHADOW:
        assert _writes_to_live_tables(path.read_text(encoding="utf-8")) == [], path


def test_the_checks_can_see_a_violation():
    """Perturbations: an import and a write must both be detected, or the two tests above prove nothing."""
    src = 'X = "UPDATE predictions SET signal = %s WHERE as_of = %s"\n'
    assert _writes_to_live_tables(src)
    assert _writes_to_live_tables('X = """\n  delete   from prediction_outcomes where id = 1"""\n')
    assert not _writes_to_live_tables('X = "SELECT close_price FROM predictions WHERE as_of = %s"\n')
    assert not _writes_to_live_tables('"""Docstring: we never UPDATE predictions."""\n')
    tmp = Path("tests/_tmp_import_probe.py")
    try:
        tmp.write_text("from agent.shadow.model import load\n", encoding="utf-8")
        assert any(i.startswith("agent.shadow") for i in _imports(str(tmp)))
    finally:
        tmp.unlink()
