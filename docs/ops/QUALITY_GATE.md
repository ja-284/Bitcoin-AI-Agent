# The quality gate: how tests, commits and pushes are run (since 2026-10-16)

**One rule:** commit and push only through `tools/gate.py`. Never chain `pytest ...; git commit ...; git push`
by hand. In PowerShell (and in most shells) `;` runs the next command whatever the previous one returned, and on
2026-10-15 that made a commit after a failing test. The gate checks every exit code itself, so its result cannot
read "success" after a failure.

```
python tools/gate.py check  [--integration] [--mutations TEXT | --all-mutations]
python tools/gate.py ship   --message-file FILE [--no-push] PATH [PATH ...] [the same options]
python tools/gate.py push   [the same options]
```

- **check** runs the steps and reports. **ship** stages exactly the given paths, runs the gate, commits only if it
  passed, then pushes. **push** runs the gate on commits already made, then pushes.
- The steps, in order:
  1. the unit tests, with a deliberately unreachable `DATABASE_URL`, as CI runs them;
  2. with `--integration`, the real-Postgres integration tests in a scratch schema they create and drop;
  3. with `--mutations TEXT` or `--all-mutations`, the mutation guards (`tools/guard_mutations.py`).
- The first failing step stops the gate. Later steps are printed **NOT RUN**, and the exit code is 1. "PASSED" is
  printed only when every step ran and returned 0.
- `ship` refuses if anything outside the given paths is modified or untracked, so the tree that was tested is the
  tree that is committed.
- A push counts as done only when `git push` returned 0 **and** the upstream branch then points at HEAD.
- GitHub's *Tests* workflow stays the independent second check after every push.

When to use which options:
- **every change:** `ship` (the unit tests);
- **a change to schema, roles or storage:** add `--integration`;
- **a change to a guarded rule:** `ship --no-push` first (the mutation tool refuses uncommitted files), then
  `push --mutations TEXT` for that area;
- **the weekly audit and the final check of a work block:** `check --integration --all-mutations`.

**How it was proven (2026-10-16):** in a throwaway clone with a local fake remote, a deliberately failing test
made `ship` exit 1 with no commit and no push. `check` with a failing first step reported the next step NOT RUN.
A passing change committed and pushed, to the fake remote only. `tests/test_gate.py` covers the same paths with a
fake git. Five mutation guards ("quality gate") break each rule on purpose.
