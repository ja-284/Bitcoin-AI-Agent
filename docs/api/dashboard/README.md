# Bitcoin AI Control Center: dashboard data contract (handoff folder)

> **A PRIVATE, READ-ONLY STATISTICS DASHBOARD. NOT THE TRADING APPLICATION.**
> Everything here describes what the dashboard may read and how to show it. Nothing here grants access, connects
> anything, or changes the backend.

| | |
|---|---|
| Reporting contract version supported | `"1"` (the only version) |
| Derived from the backend reporting code at | commit `a9abca0` (`agent/reporting`) |
| Verified on | 2026-10-22 |
| Database changes needed | none. The dashboard reads three existing tables with the access already in place (`docs/api/stats_access.md` §2). |
| Live connection | **not active.** Connecting the dashboard to real data needs the owner's separate approval and the browser test (contract v1, Part 9). |

## The files

| file | kind | purpose |
|---|---|---|
| `dashboard_data_contract_v1.md` | documentation | The original contract v1: tables, every field and its meaning, statistics and their limitations, research protections, freshness rules, page mapping, integration rules, the browser-test checklist. |
| `dashboard_contract_v1_supplement_s1.md` | documentation | Supplement S1: required / optional / nullable fields, state-dependent shapes, the validation rules, presentation and freshness rules, exclusions, and the completeness check. It contains the TypeScript, the JavaScript and the smaller fixtures inline, inserted byte-for-byte from the files below. |
| `dashboard_contract_v1.ts` | documentation (machine-readable) | The TypeScript types of the three tables and of every JSON structure. Generated from the schema that validated the live tables. **Not yet compiled.** |
| `dashboard_fixtures_v1.json` | examples (fictional) | Complete example data: `main` (a snapshot row, a run row with pending outcomes, a run row with graded outcomes, an incident row), `edge_cases` E01–E19 (states not seen live), `no_data_document`. **Every value is invented** (dates in 2030, `"fictional": true`). |
| `dashboard_reporting_client.js` | reference code | A read-only access module for supabase-js v2. **UNTESTED REFERENCE MATERIAL, NOT PRODUCTION-READY**: never executed, never type-checked. |
| `HANDOFF_MANIFEST.md` | documentation | The handoff list for Lovable (commit, checksums, order, rules). Added in a second commit, because it names the commit that added these files. |

**Which document applies where they differ.** Contract v1 §2.2 (hand-written TypeScript) and §2.3 (an abbreviated example with
placeholder strings) are kept verbatim and marked. Where they are less precise, Supplement S1 and the generated files
apply. No JSON field name and no definition differs between them; nothing mathematical or statistical was changed.

**Read them in this order:** this README → contract v1 → Supplement S1 → the `.ts` file → the fixtures → the `.js` file.

## Checks actually performed (2026-10-22)

1. **Live tables, read-only.** Every row was validated against the schema the TypeScript is generated from, with
   unknown keys counted as errors. Only error paths and counts were printed.
   - `reporting_snapshot`: 0 errors.
   - `reporting_runs`: 787 of 787 rows valid.
   - `reporting_incidents`: 17 of 17 rows valid.
   - Every field of every structure that appears live was present live.
2. **Fixtures.** They were produced by running the real reporting code (`agent.reporting.publish.build` and
   `agent.reporting.views` at `a9abca0`) on invented records.
   - All of them validate with 0 errors: the 4 main rows, E01–E19, the no-data document and all 199 run rows of the
     fictional record.
   - Every type and every field of the schema is exercised by at least one fixture.
3. **Fixture consistency.**
   - `generated_at` = `as_known_at`.
   - `overview.latest_hour` = the newest run row.
   - Saved rows + missing hours = the hours spanned.
   - The graded row's `as_known_at` reproduces its content.
4. **Documents against files.** Every code and JSON block in Supplement S1 equals the corresponding file in this
   folder. The three files are byte-identical to the validated generator output.
5. **Security and content review.** Every file in this folder, and the lines this change adds elsewhere, were scanned.
   None contains:
   - any key, token, password, database URL, TOTP URI, private key, email address, account id (UUID), Supabase host
     or IP address;
   - no `service_role` credential (the word appears only in sentences that forbid its use);
   - no direction-track data (the track is named only in sentences that forbid showing it);
   - any timestamp outside the fictional year 2030 in the fixtures.
   The documents contain no real predictions, holdout data, checkpoint pass/fail outcomes or 500-hour figures.
6. **The unit tests** ran through the project's quality gate (`tools/gate.py`) when this folder was committed. The
   result is recorded in `HANDOFF_MANIFEST.md`.

## Checks still outstanding

- **TypeScript not compiled.** No TypeScript compiler was available. Run `tsc --noEmit` before relying on the types.
- **JavaScript never executed.** No JavaScript runtime was available. Lovable must adapt it, then compile, execute and
  test it against the fixtures before any use. Until then it stays **UNTESTED**.
- **Browser behaviour not tested:** the exact HTTP codes, the shape of network errors, and whether aal2 survives a
  token refresh. These are the owner's browser test (contract v1, Part 9).
- **Some states have never occurred live:** six state types (e.g. an `unavailable` outcome, `no_data` health) and some
  enum values (e.g. `overdue`, `stale`). They are covered only by the fictional fixtures.
- **The generator is not in the repository.** The schema check and the fixture generator were a one-off verification
  script, so this check cannot yet be re-run from the repository alone. Adding it as a test would be a code change and
  needs approval.
- **If `agent/reporting` changes**, this contract must be re-checked against the new code. Nothing automatic does that
  yet.

## Not available to the dashboard

Tests & CI, experiment records, AI cost, news evaluation, readiness status, checkpoint figures, and anything from the
blind direction track or the sealed holdout are not in the three tables. Pages that need them show
"Data ikke tilgjengelig ennå" (contract v1, Part 7).
