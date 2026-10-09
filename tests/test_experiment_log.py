"""
The experiment log stays complete (research/experiments/README.md): every experiment has exactly one
JSON record and one row in research/EXPERIMENTS.md, so none can be dropped quietly, and every record
states what was fixed in advance and what happened. Added 2026-10-09, when the audit found that E014
(the sealed-holdout evaluation) had a record but no index row.
"""

import json
import re
from pathlib import Path

INDEX = Path("research/EXPERIMENTS.md")
RECORDS = Path("research/experiments")
CORE = ("id", "date", "git_commit", "status")
FIXED_IN_ADVANCE = ("hypothesis", "hypothesis_H", "hypotheses", "acceptance_criterion", "what_each_answer_means_decided_in_advance",
                    "expectation_stated_in_advance", "pass_rules_copied_unchanged", "why", "question", "method")
OUTCOME = ("results", "result", "metrics")


def _records() -> dict[str, tuple[Path, dict]]:
    out = {}
    for f in sorted(RECORDS.glob("E*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d.get("id") not in out, f"two records claim {d.get('id')}"
        out[d.get("id")] = (f, d)
    return out


def test_every_experiment_has_one_record_and_one_index_row():
    rows = re.findall(r"^\| (E\d{3}) \|", INDEX.read_text(encoding="utf-8"), re.M)
    assert len(rows) == len(set(rows)), "an experiment appears twice in the index"
    records = _records()
    assert set(rows) == set(records), (f"index without record: {sorted(set(rows) - set(records))}; "
                                       f"record without index row: {sorted(set(records) - set(rows))}")
    numbers = sorted(int(i[1:]) for i in records)
    assert numbers == list(range(numbers[0], numbers[-1] + 1)), "a gap in the experiment numbers: was one deleted?"


def test_every_record_carries_its_core_what_was_fixed_in_advance_and_what_happened():
    for i, (f, d) in _records().items():
        assert f.name.startswith(f"{i}_"), f"{f.name} does not match its id {i}"
        missing = [k for k in CORE if not d.get(k)]
        assert not missing, f"{i}: missing {missing}"
        assert any(k in d for k in FIXED_IN_ADVANCE), f"{i}: nothing records what was fixed in advance"
        assert any(k in d for k in OUTCOME), f"{i}: nothing records what happened"
