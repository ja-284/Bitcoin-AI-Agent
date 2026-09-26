# Pre-500h plan — section-by-section audit

Audit of `research/INTERIM_PLAN_PRE_500H.md`, **2026-09-26 ~14:00 UTC** (108 of 500 prospective hours).
Updated whenever a task below moves. Classification: COMPLETE · PARTIALLY COMPLETE · NOT STARTED ·
BLOCKED · CONTINUOUS MONITORING. "Complete" means tested, verified live where relevant, documented,
committed and pushed — not "written".

| | area | status | evidence | what remains |
|---|---|---|---|---|
| A | Live-system health | **CONTINUOUS MONITORING** | every session: hours, roles, sources, errors, shadow, outcomes, publish; 0 missed hours since 2026-09-20; first 168h outcomes graded 2026-09-26 under `bitcoin_agent` | the session loop; nothing open |
| B | Security and database hardening | **COMPLETE** + monitoring | RLS + revokes + default privileges closed; detector covers tables, views, functions, default grants; least-privilege role live and checked by the watchdog; Exposed schemas confirmed; drift check includes the role file; **B1 done 2026-09-26:** every action pinned to a commit SHA, tested, mutation-guarded, verified on GitHub (Tests run on `677e1c0`); **B2 done:** `tools/dependency_audit.py` — 43 installed packages, 0 known vulnerabilities | weekly: `tools/dependency_audit.py`, integration drift check |
| C | Reliability and failure recovery | **COMPLETE** (by tests) | failure modes, fallback, malformed data, gaps, stale data, rate limits (429 not retried), AI and SDK failures, empty/partial news, DB down at save, duplicates (real Postgres), late runs, publish failure, heartbeat hiccup, schema mismatch, permission drift (watchdog role check) | re-check when anything in the live path changes |
| D | Observability | **COMPLETE** + monitoring | weekly report: health, cost with week coverage, shadow record vs free rule, paper record, parity, shadow input parity, drift, watch list; watchdog; heartbeat | runtime is measured ad hoc (GitHub API), not in the report — no evidence it needs more |
| E | Performance | **COMPLETE** + monitoring | 2026-09-25: job 74–79 s, causes known, under a tenth of budget | re-measure weekly; act only on evidence |
| F | Research integrity | **COMPLETE** + guards | point-in-time tests, 44 mutation guards (43/43 in one pass), holdout guards, report = checkpoint (test), parity, E024/E025 operating characteristics | guards run on every push |
| G | Safe historical research | **PARTIALLY COMPLETE** | E025 (news power), E026 (calibration by volatility regime) | **G1** a development reference for the *other* registered checkpoint slices (weekday/weekend, hour-of-day blocks) — E026 covered only the regime slice |
| H | Research-only algorithms | **NOT STARTED** | — | **H1** a sequential calibration-drift detector (research-only): how quickly could a *persistent* offset like the E026 watch item be told apart from noise, and at what false-alarm rate — measured on development data, never wired to the model |
| I | Reproducibility / versioning | **COMPLETE** + guards | versions pinned, artefact hash, feature fingerprint, schema version, `code_commit` and `db_role` on every row, candles → inputs → probability verified for every stored hour | — |
| J | Unattended operation | **COMPLETE** | `docs/ops/STATUS.md` + `status.json`; heartbeat verified; watchdog verified under `bitcoin_agent`; storage 17 of 500 MB; staleness alarm proven | keep STATUS current each session |
| K | Checkpoint integrity | **COMPLETE** | fixed prefix, shared pass rules, frozen terciles, reproducibility precondition, report = checkpoint, refuses early — all tested; **K1 done 2026-09-26:** the command runs end to end in a test (fetch → free-rule comparison → evaluation → integrity line → both files; exactly the first 500 hours; never rewrites; writes nothing before 500) | run it at the first session after 500 graded hours |
| L | Documentation | **CONTINUOUS** | CLAUDE.md, ROADMAP, CHANGELOG, STATUS, LIVE_EVALUATION, EXPERIMENTS current | — |

**Order of work (plan priority): B1 → B2 → K1 → G1 → H1**, then monitoring. Nothing touches the frozen
predictive path; nothing reads prospective outcomes for anything but descriptive monitoring.
