"""
Supply-chain hardening (interim plan, priority B, 2026-09-26): every third-party action in every workflow is
pinned to a full commit SHA, not a movable tag. The actions run with the jobs' secrets (Anthropic key,
database URL, heartbeat URL); a repointed tag could exfiltrate them, a pinned SHA cannot change under us.
The version the SHA corresponds to is kept in a comment, so an upgrade is a deliberate, reviewable edit.
"""

import re
from pathlib import Path

WORKFLOWS = sorted(Path(".github/workflows").glob("*.yml"))
USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)(.*)$")


def _uses():
    for wf in WORKFLOWS:
        for n, line in enumerate(wf.read_text(encoding="utf-8").splitlines(), 1):
            m = USES.match(line)
            if m:
                yield wf.name, n, m.group(1), m.group(2)


def test_there_are_workflows_and_actions_to_check():
    assert len(WORKFLOWS) >= 3 and len(list(_uses())) >= 6


def test_every_action_is_pinned_to_a_full_commit_sha_with_its_version_noted():
    for name, n, ref, rest in _uses():
        if ref.startswith("./"):
            continue  # a local action lives in this repository and is reviewed with it
        assert re.fullmatch(r"[\w.-]+/[\w.-]+(/[\w./-]+)?@[0-9a-f]{40}", ref), f"{name}:{n} uses a movable reference: {ref}"
        assert re.search(r"#\s*v\d", rest), f"{name}:{n} does not note which version the SHA is"


def test_the_check_would_catch_a_tag():
    """Perturbation: a tag-pinned line must fail the pattern the test above applies."""
    assert not re.fullmatch(r"[\w.-]+/[\w.-]+(/[\w./-]+)?@[0-9a-f]{40}", "actions/checkout@v4")
