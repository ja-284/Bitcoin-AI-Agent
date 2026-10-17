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
| 2026-09-20 → 2026-10-17 | **the side-data loaders** (trade counts and taker volume, funding, premium, macro, on-chain, difficulty): every research run that computed one of these groups read the WHOLE dated file into memory, holdout rows included. Found by the 2026-10-17 inventory; closed the same day (row `snapshots.py` below) | every holdout-period row of the files used (counts: the 2026-10-17 entry below) | nothing: every feature is cut to a candle grid built from `load_bars(end=HOLDOUT.start)`, and each one reads only rows visible at its own cutoff |
| 2026-09-19 → 2026-10-17 | `load_bars()` itself parsed the whole spot snapshot into memory, then kept the rows before the holdout (and took the newest snapshot, downloading one when none existed). Closed 2026-10-17: it now reads through the same governed reader | all of it, in memory | nothing |

The EWMA rule has a 24-hour half-life. At the live hours where its values are used, every holdout candle weighs
less than 2e-10 (`research/LIVE_EVALUATION.md`, 500-hour procedure, item 3).

## Every route, reviewed (`tests/test_holdout_routes.py` fails on any new one)

| route | can it reach the holdout? |
|---|---|
| `research/history.load_bars()` | **The one governed route.** It truncates at the holdout unless `allow_holdout=True` with a written reason, and that is logged to `research/HOLDOUT_ACCESS.log`. Only `holdout_eval.py --unseal` passes it, and the test proves no other call does. Since 2026-10-17 it reads the registered spot snapshot only (`snapshots.py`, "spot"): reading stops at the holdout's first candle, the access is logged BEFORE a byte past it is read, nothing is downloaded and no newer file is taken |
| the snapshot file itself | only the registry (`snapshots.py`) and the hand-run downloader's file naming (`history.py`) may name it (tested), so no other code can read it directly |
| `agent/backtest/runner.py` | **was the bypass; closed 2026-10-14.** It now refuses, before fetching anything, any window whose candles (warm-up included) touch the holdout, and it checks what came back as a second lock. There is no override. It would have refused E000's window, and the test reproduces E000's 233 candles exactly |
| `research/parity.py` | no: live hours only, from about 2026-09-08 |
| `weekly_report.live_features` | no: from LIVE.start − 400 h, about 2026-09-02 |
| `weekly_report.ewma_reference_series` | **no, since Amendment A1 (2026-10-14).** The window is clipped at the buffer's first hour (`ewma_fetch_hours`), a window ending inside or before the holdout is refused, and the returned candles are checked. Until A1 it read holdout candles as warm-up (rows above) |
| live paths (the hourly job, outcome grading, the shadow model) | no: they fetch the latest hours, or the target hours of live predictions |
| the direction shadow track (`agent/direction_shadow`, E034, since 2026-10-15) | no. Its hourly step fetches the latest 250 closed hours; its grading fetches the target hours of its own rows, all written from 2026-10-15 on; its artefact was fitted through `build_frame`'s default, which stops at the holdout (tested) |
| `agent/research/snapshots.py`, the side snapshots' reader (since 2026-10-17) | **Only through the logged route.** It is the one reader of the six side snapshots (the loaders in `microstructure.py`, `derivatives.py`, `macro.py` and `onchain.py` call it). It serves registered files only: a fixed name, the count and sha256 of the development rows, and the whole file's size and sha256. Rows are cut by when they became visible, at the last development cutoff (2025-07-01 00:00 UTC, the close of the last development candle), and reading stops at the first row past it. Rows past it are served only after `load_bars(allow_holdout=True, reason=...)` opened the holdout in the same process; the whole file's sha256 is then checked. A missing, changed, out-of-order or unregistered file is refused, and nothing is downloaded. The macro snapshot is refused outright: its bars are not daily |
| `feature_test.compute_group_features`, the one research route to side data | It asks for side data up to the candles' own information cutoff (the close of the latest candle), so candles that stop at the holdout get side data that stops there too (tested) |
| the side snapshot files themselves | only `snapshots.py` names them, and no other file in `agent/` parses a CSV (both tested) |

Fourteen mutation guards keep these locks honest (`tools/guard_mutations.py`). Area *holdout*: two for the backtest
and one for Amendment A1's clip. Area *data-boundary*: nine for the side-data reader and two for `load_bars`.

**The registered snapshots on 2026-10-17** (scan of the timestamp column only; no value decoded). Every file is
strictly increasing in time. The development rows are those visible at or before 2025-07-01 00:00 UTC:

| snapshot | rows | development rows | rows past the cutoff | rule: a row stamped T is known from |
|---|---|---|---|---|
| `btcusdt_1h_2026-09-19.csv` (spot, `load_bars`) | 79,567 | 68,868 | 10,699 | T + 1 h |
| `klines_extra_btcusdt_1h_2026-09-20.csv` | 79,588 | 68,868 | 10,720 | T + 1 h |
| `funding_btcusdt_2026-09-20.csv` | 7,702 | 6,362 | 1,340 | T |
| `premium_btcusdt_1h_2026-09-20.csv` | 59,093 | 48,380 | 10,713 | T + 1 h |
| `onchain_2026-09-20.csv` | 6,462 | 6,022 | 440 | T + 30 h |
| `difficulty_adjustments_2026-09-20.csv` | 466 | 434 | 32 | T |
| `macro_2026-09-20.csv` (refused) | 504 | 488 | 16 | T + 22 h, as the code assumed for daily bars |

**What the evidence establishes, and what it does not.**
- **Established, from the code and its tests:** no holdout-period side value entered a development feature value.
  - Every route computed side features on a grid built from `load_bars(end=HOLDOUT.start)`.
  - Every feature reads only rows visible at its own cutoff. The garbled-future tests of each module show it, and
    `tests/test_snapshots.py` shows it again: on synthetic files, the cut leaves every development feature value
    unchanged.
- **Not established:** whether a holdout-period side value was ever shown in an interactive session. No record says
  either way. The download code logged only counts and date ranges.

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
