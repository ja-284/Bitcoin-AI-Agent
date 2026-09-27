"""
The reporting layer (agent/reporting) is downstream of production and must stay that way:

    live system -> database records -> agent.reporting (read-only) -> a future UI

  1. Nothing outside agent/reporting imports it -- not the live signal, the shadow job, the outcome
     tracker, the publish step, the research bench that judges the model, the tools, or run.py -- and
     no workflow runs it. So its output cannot become an input to a prediction, a threshold, a
     feature choice or a checkpoint.
  2. It imports only reviewed, read-only names from the rest of the project (an explicit allowlist:
     a new import fails here until someone looks at it).
  3. Its SQL is SELECT-only, it never commits or bulk-writes, and the one function that opens a
     connection makes the server hold it READ ONLY -- and fails closed if that does not stick.
  4. (2026-09-27) The one exception is the private stats publisher (agent/reporting/publish.py): it may
     write, but only the two derived-cache tables the stats website reads, and only one workflow may run
     it -- the "Reporting snapshot" workflow, which starts after the hourly one completes and runs nothing
     else. The hourly workflow does not know it exists.
Mutation guards in tools/guard_mutations.py break each of these on purpose and require a test to fail.
"""

import ast
import re
from pathlib import Path

import pytest

from agent.reporting import source

REPORTING = sorted(Path("agent/reporting").glob("*.py"))
PUBLISHER = Path("agent/reporting/publish.py")
READ_ONLY = [p for p in REPORTING if p != PUBLISHER]  # everything but the publisher: SELECT only, no writes of any kind
REPORTING_WORKFLOW = Path(".github/workflows/reporting.yml")
PRODUCTION_AND_RESEARCH = sorted(p for p in Path("agent").rglob("*.py") if "reporting" not in p.parts) + \
    [Path("run.py"), *sorted(Path("tools").glob("*.py"))]
WORKFLOWS = sorted(Path(".github/workflows").glob("*.yml"))

# Everything agent.reporting may import from the rest of the project, name by name. Read-only
# definitions and pure functions only: no save_*, track_*, publish, run or main.
ALLOWED = {
    "agent.api.state": {"CONFIDENCE_MEANING", "LIMITATIONS", "MOVE_SIZE_MEANING", "MOVE_SIZE_STATUS", "SIGNAL_EVIDENCE", "Quantity"},
    "agent.database.db": {"get_connection"},
    "agent.healthcheck": {"check"},
    "agent.outcome_tracker": {"HORIZONS_HOURS"},
    "agent.research.labels": {"DOWN", "UP"},
    "agent.research.live_checkpoint": {"BLOCK_HOURS", "CHECKPOINTS", "HOUR_BLOCKS", "OUT_DIR", "TERCILES_PATH", "_slice", "core",
                                       "prospective", "prospective_graded", "regime_of"},
    "agent.research.metrics": {"brier_score", "wilson_interval"},
    "agent.research.periods": {"HOLDOUT"},
    "agent.research.weekly_report": {"INTERVALS_NOMINAL_FROM_HOURS", "expected_hours"},
    "agent.version": {"PIPELINE_VERSION"},
}
# Whole words only (a column called created_at is not CREATE). SET, set_config and TRANSACTION are here too:
# `SET TRANSACTION READ WRITE` or set_config('transaction_read_only', ...) could undo the read-only session.
WRITE_WORDS = r"\b(INSERT|UPDATE|DELETE|TRUNCATE|CREATE|ALTER|DROP|GRANT|REVOKE|COPY|CALL|MERGE|VACUUM|LOCK|COMMENT|SET|SET_CONFIG|TRANSACTION|COMMIT|DO)\b"


def _imports(path: Path) -> list[tuple[str, str | None]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            out += [(n.module, a.name) for a in n.names]
        elif isinstance(n, ast.Import):
            out += [(a.name, None) for a in n.names]
    return out


def _imports_reporting(path: Path) -> bool:
    return any(m == "agent.reporting" or m.startswith("agent.reporting.") or (m == "agent" and name == "reporting")
               for m, name in _imports(path))


def _string_constants(source_text: str) -> list[str]:
    """String constants that are not docstrings (a docstring may mention UPDATE; it is not SQL)."""
    tree = ast.parse(source_text)
    docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                  if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
                  and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]


def sql_violations(source_text: str) -> list[str]:
    """SQL-looking strings that are not a plain read: they must start with SELECT (or WITH) and write nothing."""
    bad = []
    for s in _string_constants(source_text):
        flat = " ".join(s.split()).upper()
        if not re.search(r"\b(SELECT|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|TRUNCATE|CREATE|ALTER\s+TABLE|DROP)\b", flat):
            continue
        if not re.match(r"^(SELECT|WITH)\b", flat) or re.search(WRITE_WORDS, flat):
            bad.append(s.strip()[:80])
    return bad


def forbidden_calls(source_text: str) -> list[str]:
    """Method calls a read-only module has no business making."""
    tree = ast.parse(source_text)
    return [n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in ("commit", "executemany", "copy", "write_text", "write_bytes")]


# ------------------------------------------------------------------ 1. nothing depends on it
def test_nothing_in_production_or_research_imports_the_reporting_layer():
    assert len(PRODUCTION_AND_RESEARCH) > 60, "the scanned file list is suspiciously short"
    assert Path("agent/orchestrator.py") in PRODUCTION_AND_RESEARCH and Path("agent/shadow/run.py") in PRODUCTION_AND_RESEARCH
    offenders = [str(p) for p in PRODUCTION_AND_RESEARCH if _imports_reporting(p)]
    assert offenders == [], offenders


def test_only_the_reporting_workflow_runs_it_and_it_runs_only_the_publisher():
    assert REPORTING_WORKFLOW in WORKFLOWS and len(WORKFLOWS) >= 4
    for wf in WORKFLOWS:
        text = wf.read_text(encoding="utf-8")
        if wf != REPORTING_WORKFLOW:
            for word in ("agent.reporting", "reporting_snapshot", "reporting_runs"):
                assert word not in text, f"{wf} mentions {word}"
    text = REPORTING_WORKFLOW.read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    runs = [line.split("run:", 1)[1].strip() for line in code.splitlines() if line.strip().startswith(("run:", "- run:"))]
    assert runs == ["pip install -r requirements.txt", "python -m agent.reporting.publish"], runs
    assert "schedule" not in code and "cron" not in code, "it must have no schedule of its own"
    assert re.search(r'on:\s*\n\s*workflow_run:\s*\n\s*workflows: \["Hourly Bitcoin analysis"\]\s*\n\s*types: \[completed\]', code)
    assert re.search(r"^name: Hourly Bitcoin analysis$", Path(".github/workflows/hourly.yml").read_text(encoding="utf-8"), re.M)
    assert set(re.findall(r"secrets\.(\w+)", code)) == {"DATABASE_URL"}, "no AI key, no heartbeat URL, nothing else"
    assert re.search(r"^permissions:\s*\n\s*contents: read\s*$", code, re.M)


# ------------------------------------------------------------------ 2. it depends only on reviewed names
def test_the_reporting_layer_imports_only_reviewed_read_only_names():
    assert len(REPORTING) >= 4
    for path in REPORTING:
        for module, name in _imports(path):
            if not module.startswith("agent") or module == "agent.reporting" or module.startswith("agent.reporting."):
                continue
            assert name is not None and name in ALLOWED.get(module, set()), f"{path}: {module}.{name} is not on the reviewed list"


# ------------------------------------------------------------------ 3. it cannot write
def test_the_reporting_sql_is_select_only_and_nothing_commits_or_writes_files():
    found_sql = 0
    for path in READ_ONLY:
        text = path.read_text(encoding="utf-8")
        assert sql_violations(text) == [], path
        assert forbidden_calls(text) == [], path
        found_sql += sum(1 for s in _string_constants(text) if " ".join(s.split()).upper().startswith("SELECT"))
    assert found_sql >= 6, "the reporting SQL was not found -- the check would prove nothing"


def test_only_the_read_only_helper_opens_a_connection():
    for path in REPORTING:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
            calls = {c.func.id for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
            if "get_connection" in calls:
                assert (path.name, fn.name) in {("source.py", "read_only_connection"), ("publish.py", "_cache_connection")},                     f"{path}:{fn.name} opens its own connection"


class _Conn:
    def __init__(self, sticks=True):
        self._ro, self._sticks, self.closed = False, sticks, False

    @property
    def read_only(self):
        return self._ro

    @read_only.setter
    def read_only(self, value):
        if self._sticks:
            self._ro = value

    def close(self):
        self.closed = True


def test_the_connection_is_held_read_only_and_fails_closed(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(source, "get_connection", lambda: conn)
    assert source.read_only_connection() is conn and conn.read_only is True
    stubborn = _Conn(sticks=False)
    monkeypatch.setattr(source, "get_connection", lambda: stubborn)
    with pytest.raises(RuntimeError, match="read-only"):
        source.read_only_connection()
    assert stubborn.closed


def write_targets(source_text: str) -> list[str]:
    """Every table a SQL string constant writes to (INSERT INTO t, UPDATE t SET, DELETE FROM t, TRUNCATE t)."""
    found = []
    for s in _string_constants(source_text):
        flat = " ".join(s.split()).upper()
        found += re.findall(r"\bINSERT\s+INTO\s+(\w+)", flat) + re.findall(r"\bUPDATE\s+(\w+)\s+SET\b", flat)
        found += re.findall(r"\bDELETE\s+FROM\s+(\w+)", flat) + re.findall(r"\bTRUNCATE\s+(?:TABLE\s+)?(\w+)", flat)
    return [t.lower() for t in found]


def test_the_publisher_writes_only_the_two_cache_tables_the_website_reads():
    from agent.database.security import VIEWER_READ_TABLES
    from agent.reporting import publish

    text = PUBLISHER.read_text(encoding="utf-8")
    targets = write_targets(text)
    assert sorted(set(targets)) == sorted(publish.CACHE_TABLES) and len(targets) >= 2, targets
    assert tuple(publish.CACHE_TABLES) == VIEWER_READ_TABLES, "the website may read exactly what the publisher writes"
    for s in _string_constants(text):
        flat = " ".join(s.split()).upper()
        assert not re.search(r"\b(CREATE|ALTER|DROP|GRANT|REVOKE|COPY|CALL|SET_CONFIG|TRANSACTION|DELETE|TRUNCATE)\b", flat), s[:60]
    assert [c for c in forbidden_calls(text) if c not in ("commit", "executemany")] == []
    for path in READ_ONLY:  # the read side never depends on the write side
        assert not any(m == "agent.reporting.publish" or (m == "agent.reporting" and n == "publish")
                       for m, n in _imports(path)), path


# ------------------------------------------------------------------ the checks themselves
def test_the_guards_can_see_a_violation():
    """Perturbations: each check must fire on a real violation, or the tests above prove nothing."""
    assert sql_violations('X = "UPDATE predictions SET signal = %s WHERE as_of = %s"\n')
    assert sql_violations('X = """\n insert into prediction_outcomes (prediction_id) values (1)"""\n')
    assert sql_violations('X = "WITH x AS (DELETE FROM shadow_move_size RETURNING *) SELECT * FROM x"\n')
    assert sql_violations('X = "SELECT set_config(\'a\', \'b\', false); DROP TABLE predictions"\n')
    assert sql_violations('X = "SELECT set_config(\'transaction_read_only\', \'off\', true)"\n')
    assert sql_violations('X = "SELECT 1; SET TRANSACTION READ WRITE"\n')
    assert not sql_violations('X = "SELECT as_of, signal FROM predictions WHERE as_of = %s ORDER BY as_of"\n')
    assert not sql_violations('"""Docstring: this module never runs UPDATE predictions."""\n')
    assert forbidden_calls("conn.commit()\n") == ["commit"]
    assert forbidden_calls("Path('x').write_text('y')\n") == ["write_text"]
    assert write_targets('X = "INSERT INTO predictions (id) VALUES (1)"\n') == ["predictions"]
    assert write_targets('X = """ update  prediction_outcomes set status = 1"""\n') == ["prediction_outcomes"]
    assert write_targets('X = "INSERT INTO reporting_runs (hour) VALUES (1) ON CONFLICT (hour) DO UPDATE SET run = 1"\n') == ["reporting_runs"]
    probe = Path("agent/_reporting_import_probe_tmp.py")
    try:
        probe.write_text("from agent.reporting.views import report\n", encoding="utf-8")
        assert _imports_reporting(probe)
        probe.write_text("from agent import reporting\n", encoding="utf-8")
        assert _imports_reporting(probe)
    finally:
        probe.unlink()
