"""
The quality gate, and the one way to commit and push in this project (master plan addendum, 2026-10-16, item 3).

    python tools/gate.py check [--integration] [--mutations TEXT | --all-mutations]
    python tools/gate.py ship  --message-file FILE [--no-push] PATH [PATH ...] [same options]
    python tools/gate.py push  [same options]

Why it exists. On 2026-10-15 a hand-written PowerShell sequence `pytest ...; git commit ...` made a commit after a
failing test, because `;` runs the next command whatever the previous one returned. GitHub's CI catches a failure
after a push; this stops it before.

The rules, each tested in tests/test_gate.py:
  * Steps run in order. Each step's real exit code is read, and the first non-zero code STOPS the gate. Every later
    step is reported NOT RUN, never as passed.
  * The gate's own exit code is 0 only when every step ran and returned 0. "PASSED" is printed only then.
  * ship stages exactly the given paths and refuses if anything else in the tree is modified or untracked, so the
    tree that was tested is the tree that is committed. It commits only after the gate passed, then pushes.
  * push refuses a dirty tree, runs the gate on the committed tree, pushes only if the gate passed, checks
    git push's own exit code, and then checks that the upstream branch really points at HEAD.

It is a plain script, not a git hook: nothing runs behind anyone's back, and CI stays the independent second check.
The unit tests run with a deliberately unreachable DATABASE_URL, exactly as CI runs them.
"""

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNREACHABLE_DB = "postgresql://nobody:nothing@127.0.0.1:1/none"


@dataclass
class Step:
    name: str
    cmd: list[str]
    env: dict[str, str | None] = field(default_factory=dict)  # None removes the variable


@dataclass
class Result:
    name: str
    status: str            # PASSED | FAILED | NOT RUN
    code: int | None
    seconds: float = 0.0
    detail: str = ""


@dataclass
class Report:
    results: list[Result]

    @property
    def ok(self) -> bool:
        return bool(self.results) and all(r.status == "PASSED" and r.code == 0 for r in self.results)

    def text(self) -> str:
        lines = ["", "quality gate:"]
        for r in self.results:
            code = "-" if r.code is None else str(r.code)
            lines.append(f"  {r.status:8s} exit {code:>3s}  {r.seconds:7.1f} s  {r.name}{('  (' + r.detail + ')') if r.detail else ''}")
        lines.append("RESULT: PASSED (every step ran and returned 0)" if self.ok else "RESULT: FAILED (see above; nothing further was done)")
        return "\n".join(lines)


def steps(integration: bool = False, mutations: str | None = None, all_mutations: bool = False) -> list[Step]:
    py = sys.executable
    out = [Step("unit tests (no database reachable, as in CI)", [py, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"],
                {"DATABASE_URL": UNREACHABLE_DB, "BITCOIN_AGENT_DB_TESTS": None, "PYTHONPATH": str(ROOT)})]
    if integration:
        # the real database from .env, in a scratch schema the tests create and drop
        out.append(Step("integration tests (real Postgres, scratch schema)", [py, "-m", "pytest", "tests/integration", "-q", "-p", "no:cacheprovider"],
                        {"BITCOIN_AGENT_DB_TESTS": "1", "DATABASE_URL": None, "PYTHONPATH": str(ROOT)}))
    if all_mutations:
        out.append(Step("mutation guards (all)", [py, "tools/guard_mutations.py"], {"PYTHONPATH": str(ROOT)}))
    elif mutations:
        out.append(Step(f"mutation guards matching {mutations!r}", [py, "tools/guard_mutations.py", "--only", mutations], {"PYTHONPATH": str(ROOT)}))
    return out


def _env(overrides: dict[str, str | None]) -> dict[str, str]:
    env = dict(os.environ)
    for k, v in overrides.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    return env


def run_steps(todo: list[Step], run=subprocess.run) -> Report:
    """Run in order; the first failure stops everything after it."""
    results: list[Result] = []
    for i, s in enumerate(todo):
        t0 = time.monotonic()
        try:
            code = run(s.cmd, cwd=ROOT, env=_env(s.env)).returncode
            detail = ""
        except Exception as exc:  # noqa: BLE001 -- a step that cannot even start has failed
            code, detail = 1, f"could not run: {type(exc).__name__}: {exc}"
        status = "PASSED" if code == 0 else "FAILED"
        results.append(Result(s.name, status, code, time.monotonic() - t0, detail))
        if code != 0:
            results += [Result(rest.name, "NOT RUN", None) for rest in todo[i + 1:]]
            break  # the first failure stops the gate
    return Report(results)


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def _changed_paths(porcelain: str) -> list[tuple[str, str]]:
    """(two-letter status, path) for every line of `git status --porcelain`."""
    out = []
    for line in porcelain.splitlines():
        if line.strip():
            path = line[3:].split(" -> ")[-1].strip('"')
            out.append((line[:2], path))
    return out


def _covered(path: str, allowed: list[str]) -> bool:
    p = path.replace("\\", "/").rstrip("/")
    return any(p == a or p.startswith(a.rstrip("/") + "/") for a in (x.replace("\\", "/") for x in allowed))


def push_after_gate(gate: Report, git=git) -> int:
    """Push only if the gate passed; then verify the upstream really points at HEAD."""
    if not gate.ok:  # never push after a failed gate
        print("NOT pushed: the quality gate failed.")
        return 1
    r = git("push", "-q")
    if r.returncode != 0:
        print(f"NOT pushed: git push returned {r.returncode}: {r.stderr.strip()[:300]}")
        return 1
    head, up = git("rev-parse", "HEAD").stdout.strip(), git("rev-parse", "@{u}").stdout.strip()
    if not head or head != up:
        print(f"push returned 0, but the upstream is {up[:7] or '?'} and HEAD is {head[:7] or '?'}: treat as NOT pushed")
        return 1
    print(f"pushed: the upstream now points at {head[:7]}")
    return 0


def ship(message_file: str, paths: list[str], todo: list[Step], git=git, run_gate=run_steps, push_too: bool = True) -> int:
    if not paths:
        print("refusing: name the paths to commit")
        return 2
    if not Path(message_file).is_file():
        print(f"refusing: no message file {message_file}")
        return 2
    changed = _changed_paths(git("status", "--porcelain").stdout)
    if not changed:
        print("nothing to commit")
        return 2
    stray = [p for _, p in changed if not _covered(p, paths)]
    if stray:
        print("refusing: these changes are not among the paths to commit, so the tested tree would not be the "
              "committed tree. Commit, stash or revert them first:\n  " + "\n  ".join(stray))
        return 2
    if git("add", "--", *paths).returncode != 0:
        print("refusing: git add failed")
        return 2
    leftover = [(s, p) for s, p in _changed_paths(git("status", "--porcelain").stdout) if s[1] != " "]
    if leftover:
        print(f"refusing: unstaged changes remain after staging: {leftover}")
        return 2
    gate = run_gate(todo)
    print(gate.text())
    if not gate.ok:  # never commit after a failed gate
        print("NOT committed: the quality gate failed (the changes stay staged; nothing else was done).")
        return 1
    c = git("commit", "-q", "-F", message_file)
    if c.returncode != 0:
        print(f"NOT committed: git commit returned {c.returncode}: {c.stderr.strip()[:300]}")
        return 1
    print("committed: " + git("log", "--oneline", "-1").stdout.strip())
    if not push_too:
        print("not pushed (--no-push): run `python tools/gate.py push ...` next, which runs the gate again first")
        return 0
    return push_after_gate(gate, git=git)


def push(todo: list[Step], git=git, run_gate=run_steps) -> int:
    if git("status", "--porcelain").stdout.strip():
        print("refusing: the working tree is not clean, so the gate would not test what is pushed")
        return 2
    ahead = git("rev-list", "--count", "@{u}..HEAD").stdout.strip()
    if ahead == "0":
        print("nothing to push")
        return 0
    gate = run_gate(todo)
    print(gate.text())
    return push_after_gate(gate, git=git)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "ship", "push"):
        p = sub.add_parser(name)
        p.add_argument("--integration", action="store_true", help="also run the real-Postgres integration tests")
        g = p.add_mutually_exclusive_group()
        g.add_argument("--mutations", metavar="TEXT", help="also run the mutation guards whose description contains TEXT")
        g.add_argument("--all-mutations", action="store_true", help="also run every mutation guard (slow)")
        if name == "ship":
            p.add_argument("--message-file", required=True)
            p.add_argument("--no-push", action="store_true",
                           help="commit only; for changes whose mutation guards must run on committed files before the push")
            p.add_argument("paths", nargs="+")
    a = ap.parse_args(argv)
    todo = steps(a.integration, a.mutations, a.all_mutations)
    if a.cmd == "check":
        report = run_steps(todo)
        print(report.text())
        return 0 if report.ok else 1
    if a.cmd == "ship":
        return ship(a.message_file, a.paths, todo, push_too=not a.no_push)
    return push(todo)


if __name__ == "__main__":
    raise SystemExit(main())
