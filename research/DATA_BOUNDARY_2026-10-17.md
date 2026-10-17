# The historical data boundary: Phase 1 report (2026-10-17)

*Master plan "Safe signal research, data integrity, and evidence-driven model improvement", Phase 1. It started from
the read-only signal inventory of 2026-10-17, which found that several extra-data loaders did not restrict their files
to the development period and could download replacement data silently.*

## 1. Affected loaders and routes (verified from the code)

| loader | file it read | what it did until 2026-10-17 |
|---|---|---|
| `microstructure.load_klines_extra` | `klines_extra_btcusdt_1h_2026-09-20.csv` | read the whole file; took the newest file of its kind; downloaded one if none existed |
| `derivatives.load_funding` | `funding_btcusdt_2026-09-20.csv` | the same |
| `derivatives.load_premium` | `premium_btcusdt_1h_2026-09-20.csv` | the same |
| `macro.load_macro` | `macro_2026-09-20.csv` | the same |
| `onchain.load_onchain` | `onchain_2026-09-20.csv` | the same |
| `onchain.load_difficulty` | `difficulty_adjustments_2026-09-20.csv` | the same |
| `history.load_bars` (not in the plan's list; same defect, so fixed too, with the user's agreement) | `btcusdt_1h_2026-09-19.csv` | parsed the whole file before cutting it at the holdout; took the newest snapshot; downloaded one if none existed |

- **The one research route to side data** is `feature_test.compute_group_features`. `model_test.build_frame` and
  everything built on it (E011–E035, the artefact exports, the drift reference) reach side data through it.
- **No live module and no workflow** calls any of these loaders. Verified by an AST call-site scan of `agent/`,
  `run.py` and every `python -m` target in `.github/workflows/` (now a test).

## 2. What the files hold (a structural scan of the timestamp column only; no value decoded)

Every file is strictly increasing in time. "Development rows" are those visible at or before the last development
cutoff, 2025-07-01 00:00 UTC (the close of the 2025-06-30 23:00 candle), under each dataset's own point-in-time rule.

| file | rows | development rows | rows past the cutoff |
|---|---|---|---|
| spot candles | 79,567 | 68,868 | 10,699 |
| trade counts and taker volume | 79,588 | 68,868 | 10,720 |
| funding | 7,702 | 6,362 | 1,340 |
| premium | 59,093 | 48,380 | 10,713 |
| on-chain | 6,462 | 6,022 | 440 |
| difficulty | 466 | 434 | 32 |
| macro | 504 | 488 | 16 |

**A defect found by the same scan: the macro snapshot is not daily.**
- It holds one bar per quarter (S&P, Nasdaq, dollar, 10-year yield) or roughly per month (gold, oil).
- Each bar is stamped at its start and holds the close at its end. Two S&P rows were checked against published
  closes: 2020-03-01 → the 2020-05-29 close; 2022-06-01 → the 2022-08-31 close.
- Read as daily closes visible at D 22:00 UTC, each value was used up to about three months before it existed.
- Consequences:
  - E006 is void, and E011's set B is void as a test of its registered inputs;
  - the dollar/yield watch-list item is withdrawn;
  - dated corrections were added, nothing earlier was rewritten (`beb6c6b`).
- No live path, frozen model, registered checkpoint or planned experiment uses macro data.

## 3. What changed (each change its own gated commit, pushed, CI green)

| commit | change |
|---|---|
| `ec4db68` | `agent/research/snapshots.py`: the one reader of the six side snapshots. Registered files only: a fixed name, the count and sha256 of the development rows, and the whole file's size and sha256. Rows are cut by visibility at the last development cutoff, and reading stops at the first row past it. Past it only after `load_bars(allow_holdout=True, reason=...)` opened the holdout in the same process (logged); the whole file's sha256 is then checked. A missing, changed, out-of-order or unregistered file is refused; nothing is downloaded and no other file is substituted. The macro snapshot is refused. `compute_group_features` asks for side data up to the candles' own cutoff |
| `59aa794` | `load_bars` reads the registered spot snapshot through the same reader: cut at the holdout, the access logged before a byte past it is read, no download, no newer file |
| `beb6c6b` | the macro corrections (records, index, summaries, ROADMAP, directional assessment, audit, data sources, CLAUDE.md, the weekly report's watch list) |
| this commit | this report; the written review of `beb6c6b` in `research/CHECKPOINT_PATH_REVIEWS.json` (it touched `weekly_report.py`); CLAUDE.md |

Unchanged: every feature definition, model, threshold, target, scoring rule, live path, workflow, database object and
registered checkpoint rule. `move_size_1h_v1` is untouched; the direction track's rows were counted only.

## 4. Tests and their exact results

| check | result |
|---|---|
| unit tests (no database reachable, as in CI) | 787 passed at `ec4db68`; 788 at `59aa794` and `beb6c6b` (43 integration tests skipped there and run separately) |
| integration tests (real Postgres, scratch schema, live drift check) | 43 of 43 at `ec4db68` and again at `59aa794` |
| mutation guards, area *data-boundary* | 9 of 9 caught at `ec4db68`; 11 of 11 at `59aa794`; both controls held each time; every file restored byte for byte |
| `python -m agent.database.security` | OK: 13 tables, RLS on, nothing exposed |
| `python -m agent.database.role_check` | OK: `bitcoin_agent` exactly as `docs/ops/least_privilege_role.sql` (28 policies) |
| GitHub *Tests* | success for `ec4db68`, `59aa794` and `beb6c6b` |
| `python -m agent.research.checkpoint_precheck` | exit 3 (606 of 2,000 graded hours), every mandatory item PASS, rule 3 listing `beb6c6b` as reviewed |

What the new tests cover (`tests/test_snapshots.py`, synthetic files only; route tests in `tests/test_holdout_routes.py`):

| the plan's requirement (1.3) | test |
|---|---|
| a dataset with rows beyond the boundary | each loader serves exactly the rows visible at the cutoff. The first later row carries "SEALED" values, and the bytes after it are not even valid UTF-8, so a load that succeeds proves nothing past the boundary was decoded |
| a missing dataset | refused; no download (every downloader and `requests.get` replaced by a failure); a newer file of the same kind is not substituted; nothing written |
| an unexpected version or provenance | an edited value, a dropped row, a changed header, out-of-order or duplicated rows, an unregistered name: all refused. A changed holdout-period row is refused on the logged route |
| every affected loader and route | parametrised over the five served side datasets, plus the spot candles and the refused macro snapshot. `compute_group_features` passes each candle set's own cutoff and refuses candles reaching into the holdout |
| a route that tries to bypass the loader | only `snapshots.py` parses a CSV in `agent/`; only it names the side files; only the loaders call the reader; nothing calls a downloader |
| the original files remain unchanged | on this machine, every registered file's size and development fingerprint match, and loading changes neither size nor modification time (development rows only; skipped where the files are absent, as on GitHub) |
| live and prospective workflows unaffected | no live module or workflow target calls a governed loader; both frozen models load and verify their input definitions with no snapshot, no data directory and no network |
| (added) the cut changes no development result | on synthetic files, every development feature value from the cut data equals the value from the whole file (trade counts, shape, derivatives, on-chain) |

## 5. What the evidence establishes, and what it does not

- **Unexpected data WERE read into memory before.** Every research run that computed trade-count, taker, shape,
  derivatives, macro or on-chain features loaded the whole side file, holdout rows included. Every call of `load_bars`
  parsed the whole spot file, holdout candles included.
- **No scored outcome was affected by holdout data. This is established from the code and tests:**
  - every route computed features on a grid built from `load_bars(end=HOLDOUT.start)`;
  - every feature reads only rows visible at its own cutoff (the modules' garbled-future tests, and the new identity
    test).
  - So no holdout-period value entered a development feature value, and no holdout hour was scored.
- **Development results were affected by the macro defect.** That is a look-ahead inside the development period, not
  holdout data. It makes E006 and E011's set B void. Nothing else used macro data.
- **Not established:**
  - whether a holdout-period value was ever shown in an interactive session (no record says either way);
  - that the registered files are byte-identical to what the earlier experiments read. Only one file of each kind
    exists on this machine, each modified on 2026-09-19 or 2026-09-20 (before E003), so the old "newest file" rule
    would have picked these. Whether another file ever existed is not recorded. Phase 3's reproduction of E013 and
    E032 checks it on real data.

## 6. Remaining limitations

- **Revision risk.** The fingerprints prove the files are unchanged since registration, not that each value is the one
  first published. Funding is documented as not revised. The revision risk of on-chain data (hash rate is an
  estimate, fees are priced in USD) remains as recorded in the inventory.
- **Replay caches.** `data/replays/*` is derived from the governed candles and is development-only by name and
  range. It is not fingerprinted in the registry. Phase 3's reproductions check it indirectly.
- **Downloaders.** They still exist for a hand-run, deliberate new snapshot. A new file is served only after it is
  registered in a reviewed commit.
- **Macro.** Macro information remains untestable until a daily snapshot is registered (the user's decision: not
  now).

## 7. Phase boundary

Phase 1's requirements are met:
- the protections are implemented, tested and mutation-checked;
- every commit is on GitHub with green CI;
- the working tree is clean;
- this report is written.

**Phase 2 (registration only) is permitted** (the user's instruction, 2026-10-17). Phase 3 and later are not started.
