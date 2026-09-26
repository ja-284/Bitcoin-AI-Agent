"""
docs/ops/STATUS.md and docs/ops/status.json: one dated snapshot, no contradictions between the two, and no
drift from the code they describe.

Both files are written by hand at working sessions (there is no generator). The live figures come from the
commands named in STATUS.md's snapshot table; this test cannot know the live values, but it makes sure a
session cannot leave the two files disagreeing, with a second competing timestamp, or naming versions,
a checkpoint command or a holdout state that the repository contradicts.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from agent.api.state import CONTRACT_VERSION
from agent.database.db import SCHEMA_VERSION
from agent.scoring.scorer import SCORING_VERSION
from agent.shadow.model import DEFAULT_VERSION
from agent.version import PIPELINE_VERSION

STATUS_MD = Path("docs/ops/STATUS.md")
STATUS_JSON = Path("docs/ops/status.json")
CHECKPOINT_COMMAND = "python -m agent.research.live_checkpoint"


def _md() -> str:
    return STATUS_MD.read_text(encoding="utf-8")


def _js() -> dict:
    return json.loads(STATUS_JSON.read_text(encoding="utf-8"))


def _utc(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def test_one_snapshot_time_shared_by_both_files():
    stamps = re.findall(r"\*\*Snapshot taken (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) UTC\.\*\*", _md())
    assert len(stamps) == 1, "STATUS.md must carry exactly one snapshot time"
    assert stamps[0] == _utc(_js()["as_of"]).strftime("%Y-%m-%d %H:%M")
    assert not re.search(r"\*\*As of ", _md()), "a second, competing 'As of' header is how the file went stale before"


def test_the_prospective_count_agrees_and_was_counted_by_the_snapshot_time():
    p = _js()["prospective"]
    assert f"**{p['graded_shadow_hours']} of {p['next_checkpoint_hours']}**" in _md()
    assert _utc(p["counted_at"]) <= _utc(_js()["as_of"])
    assert p["next_checkpoint_expected"][:10] in _md()


def test_versions_match_the_code():
    prod = _js()["production"]
    assert (prod["pipeline_version"], prod["scoring_version"], prod["schema_version"], prod["contract_version"],
            prod["shadow_model"]) == (PIPELINE_VERSION, SCORING_VERSION, SCHEMA_VERSION, CONTRACT_VERSION, DEFAULT_VERSION)
    md = _md()
    for text in (f"pipeline **{PIPELINE_VERSION}**", f"scoring **{SCORING_VERSION}**", f"**`{DEFAULT_VERSION}`**",
                 f"schema **{SCHEMA_VERSION}**", f"contract **v{CONTRACT_VERSION}**"):
        assert text in md, text


def test_the_mode_and_the_readiness_score_are_the_same_everywhere():
    assert _js()["mode"] == "PRE-500H MONITORING-ONLY"
    assert "## Mode: PRE-500H MONITORING-ONLY" in _md()
    gate = _js()["production"]["readiness_gate"]
    score = f"{gate['pass']} PASS, {gate['partial']} PARTIAL"
    assert f"**{score}**" in _md()
    assert score in Path("docs/research/readiness_gate.md").read_text(encoding="utf-8").split("\n\n")[1]


def test_the_holdout_claim_matches_the_repository():
    sealed = not Path("research/HOLDOUT_ACCESS.log").exists()
    assert (_js()["production"]["holdout"] == "sealed") == sealed
    assert ("**sealed**" in _md()) == sealed


def test_the_checkpoint_command_is_the_same_everywhere_and_gives_no_verdict_at_500():
    p = _js()["prospective"]
    assert p["next_checkpoint_command"] == CHECKPOINT_COMMAND == _js()["sources_of_truth"]["graded_shadow_hours"]
    assert p["next_checkpoint_gives_verdict"] is False
    for doc in (STATUS_MD, Path("research/LIVE_EVALUATION.md"), Path("CLAUDE.md")):
        assert CHECKPOINT_COMMAND in doc.read_text(encoding="utf-8"), doc
    assert Path("agent/research/live_checkpoint.py").exists()


def test_no_trading_capability_and_the_execution_note_is_marked_not_active():
    assert _js()["production"]["trading_capability"] is False
    note = Path("docs/FUTURE_EXECUTION_ARCHITECTURE.md").read_text(encoding="utf-8")
    assert note.startswith("# Future execution architecture — NOT ACTIVE")
