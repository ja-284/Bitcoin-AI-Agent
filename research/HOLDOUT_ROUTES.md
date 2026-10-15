# The sealed holdout: its exact state and every route into it

*Written 2026-10-14 (post-500h plan, Phase 5). The full history is `research/AUDIT_2026-10-08.md` §18.2. This file
adds the route review and the bypass fix. It is not the access log: that file, `research/HOLDOUT_ACCESS.log`,
must not exist until the user opens the holdout.*

The holdout is **2025-07-01 00:00 → 2026-08-19 23:00 UTC** (`agent/research/periods.py`).

## Its state, stated exactly

**Sealed for evaluation, not untouched.**

**What has never happened:**
- no holdout hour has been scored by any model or rule;
- no holdout result has been computed, shown or used for any choice;
- E014 and E023 have never run;
- `research/HOLDOUT_ACCESS.log` does not exist.

**What has happened** (raw candles read as *inputs*; no holdout hour judged):

| when | what read holdout-period candles | how many | what was scored |
|---|---|---|---|
| 2026-09-19 | the E000 technical backtest's 250-hour indicator warm-up, which **bypassed the loader's guard** | 233 candles, 2026-08-10 07:00 → 08-19 23:00 | only buffer hours (2026-08-20 → 09-19) |
| since 2026-09-22 | the weekly report's free EWMA rule's warm-up | about 71 candles, from ~2026-08-17 01:00 | only live hours |
| 2026-10-13 | the 500-hour checkpoint's free EWMA rule's warm-up (it grows with the live span) | back to ~2026-07-26 | only the 500 live hours |
| 2026-09-19 | the dated snapshot `data/btcusdt_1h_2026-09-19.csv` stores the whole period on disk | all of it | nothing (storage only) |

The EWMA rule has a 24-hour half-life. At the live hours where its values are used, every holdout candle weighs
less than 2e-10 (`research/LIVE_EVALUATION.md`, 500-hour procedure, item 3).

## Every route, reviewed (`tests/test_holdout_routes.py` fails on any new one)

| route | can it reach the holdout? |
|---|---|
| `research/history.load_bars()` | **The one governed route.** It truncates at the holdout unless `allow_holdout=True` with a written reason, and that is logged to `research/HOLDOUT_ACCESS.log`. Only `holdout_eval.py --unseal` passes it, and the test proves no other call does |
| the snapshot file itself | only `history.py` may name it (tested), so no other code can read it directly |
| `agent/backtest/runner.py` | **was the bypass; closed 2026-10-14.** It now refuses, before fetching anything, any window whose candles (warm-up included) touch the holdout, and it checks what came back as a second lock. There is no override. It would have refused E000's window, and the test reproduces E000's 233 candles exactly |
| `research/parity.py` | no: live hours only, from about 2026-09-08 |
| `weekly_report.live_features` | no: from LIVE.start − 400 h, about 2026-09-02 |
| `weekly_report.ewma_reference_series` | **no, since Amendment A1 (2026-10-14).** The window is clipped at the buffer's first hour (`ewma_fetch_hours`), a window ending inside or before the holdout is refused, and the returned candles are checked. Until A1 it read holdout candles as warm-up (rows above) |
| live paths (the hourly job, outcome grading, the shadow model) | no: they fetch the latest hours, or the target hours of live predictions |
| the direction shadow track (`agent/direction_shadow`, E034, since 2026-10-15) | no. Its hourly step fetches the latest 250 closed hours; its grading fetches the target hours of its own rows, all written from 2026-10-15 on; its artefact was fitted through `build_frame`'s default, which stops at the holdout (tested) |

Three mutation guards keep these locks honest (`tools/guard_mutations.py`, area *holdout*: two for the backtest,
one for Amendment A1's clip).

## Still open, for the user (nothing changed without a decision)

1. ~~The checkpoint's EWMA warm-up keeps reaching further into the holdout as the live record grows.~~
   **Resolved 2026-10-14 by Amendment A1** (`research/LIVE_EVALUATION.md`, protocol 1.1, registered before the
   2,000-hour reading at the user's instruction). The warm-up starts no earlier than the buffer's first hour, so it
   no longer reads the holdout, and this is enforced and tested. The effect on the rule's values is a stated bound
   (≤ ~3e-10), not a measurement, because measuring it would mean reading the holdout again. The 500-hour reading
   was made under the old warm-up and is left as written.
2. **The E000 read cannot be undone.** Its 233 candles were indicator inputs for buffer hours. The holdout's
   one-time evaluation (E014/E023) scores none of the buffer, and nothing was learned about holdout outcomes.
3. **Opening the holdout** stays the user's explicit decision, through `holdout_eval --unseal`, and only after
   the readiness conditions in `docs/research/readiness_gate.md`. As of revision 3 it is not ready.
