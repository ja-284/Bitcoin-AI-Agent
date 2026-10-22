# Handoff manifest: Bitcoin AI Control Center dashboard data contract

> **A PRIVATE, READ-ONLY STATISTICS DASHBOARD. NOT THE TRADING APPLICATION.**
> This manifest hands the data contract to the frontend build (Lovable). It authorises no live connection and no
> backend change.

| | |
|---|---|
| Repository folder | `docs/api/dashboard/` |
| Commit that added the files | `e3661b25bf3e80e4cd2a98e147182f7fe52da140` (`e3661b2`), 2026-10-22 |
| Source backend commit (reporting code the contract was derived from) | `a9abca0` |
| Reporting contract version | `"1"` |
| Quality gate for `e3661b2` | PASSED: unit tests 841 passed, 50 skipped, run with no database reachable, as in CI |
| GitHub CI for `e3661b2` | the `Tests` workflow succeeded (run 39808147873, 2026-10-22 15:47 UTC) |
| Supabase privileges or database changes needed | **none** |

## Files, checksums and verification status

SHA-256 of the exact bytes committed in `e3661b2` (LF line endings). A copy that was converted to CRLF on Windows will
have a different checksum but the same content.

| file | bytes | SHA-256 | kind | verification status |
|---|---:|---|---|---|
| `README.md` | 6,362 | `fbe7412348ff0fe2bba021943c19ba7376ec9a9109731868e731579c45c88a89` | documentation | reviewed |
| `dashboard_data_contract_v1.md` | 69,267 | `f07d428da6f00fb055ae999e5da8641d5ba4aed1551c7e9e0ef6c45d970ef2e0` | documentation | field structure checked against the live tables (read-only); §2.2 and §2.3 are marked as superseded by S1 |
| `dashboard_contract_v1_supplement_s1.md` | 96,775 | `42cad21563d3a8a88f3561951f407b867610a4a03a7be65c99ba3bc19ee109ba` | documentation | its code and JSON blocks were checked equal to the files below |
| `dashboard_contract_v1.ts` | 22,257 | `c54abcc7fe8714066c2112c160aa64ffc5de20492e9b424dbf47d1cf7c4c1a29` | types | generated from the schema that validated the live tables (0 errors) and every fixture; **NOT COMPILED** |
| `dashboard_fixtures_v1.json` | 164,149 | `48cd5ed396e1907cf252b04f2690627262c1ab81e615518bfecfac902b69a494` | fictional examples | valid JSON; produced by the real reporting code on invented 2030 records; every fixture validates against the schema (0 errors) |
| `dashboard_reporting_client.js` | 20,293 | `774527e284297be5aa485d1fbb159d372786893a9b5061f2f0235e9f5a5e3ccf` | reference code | **UNTESTED: never executed or type-checked. Not production-ready.** |
| `HANDOFF_MANIFEST.md` | — | — | this file | — |

## Known limitations

- The TypeScript has not been compiled, and the JavaScript has never run: no compiler or runtime was available.
- Browser behaviour has not been tested: the exact HTTP error codes, the shape of network errors, and whether aal2
  survives an automatic token refresh.
- Some states have never occurred in live data and are covered only by fictional fixtures:
  - `unavailable` and `overdue` outcomes;
  - `stale` and `no_data` health;
  - absent `running_figures`;
  - the volatility groups `mid`, `high` and `unknown`;
  - publisher incidents.
- The contract matches the reporting code at `a9abca0`. If `agent/reporting` changes, the contract must be re-checked.
  Nothing automatic does that yet.
- Not available to the dashboard at all (show "Data ikke tilgjengelig ennå"):
  - Tests & CI, experiments, AI cost, news evaluation, readiness status, checkpoint figures;
  - anything from the blind direction track or the sealed holdout.

## Order in which Lovable should read and use the files

1. `README.md`: what each file is, and what was and was not checked.
2. `dashboard_data_contract_v1.md`: the meaning of every field, the labelling rules, the page mapping and the browser
   checklist. §2.2 and §2.3 are superseded by the next three files.
3. `dashboard_contract_v1_supplement_s1.md`: required, optional and nullable fields, the validation rules, and the
   presentation and freshness rules.
4. `dashboard_contract_v1.ts`: copy it into the frontend as the type definitions, then run `tsc --noEmit`.
5. `dashboard_fixtures_v1.json`: the test data for every page and every state:
   - `main` for normal rendering;
   - `edge_cases` E01–E19 and `no_data_document` for the states not seen live.
6. `dashboard_reporting_client.js`: **last, and only as a reference.**

## Rules for the build

- **Test the JavaScript; do not copy it blindly.** Adapt it to the frontend's existing client. Then compile it,
  execute it and test it against `dashboard_fixtures_v1.json`, including:
  - an unsupported version;
  - a missing section;
  - unknown keys and unknown enum values;
  - inconsistent timestamps;
  - a run row newer than the snapshot;
  - the freshness clocks at 89, 91 and 181 minutes, and at −10 minutes.
  It stays UNTESTED until that is done.
- **Demo mode stays on.**
  - Build and test against the fictional fixtures only.
  - Live data is enabled only after the owner's separate approval and the browser test (contract v1, Part 9).
  - Demo data must never appear as a fallback on a live page.
- **No new access.** The dashboard needs only:
  - the Supabase project URL;
  - the publishable key;
  - the dedicated account's two-factor (aal2) session, with SELECT on three tables.
  It must not use Lovable's built-in Supabase integration, a `service_role` key, a database URL, any write, any
  database function or any other table. No RLS policy, grant or table changes for the dashboard.
- **Fixtures are fictional.** Their numbers must never be shown as real results.
- **No trading language and no verdicts:**
  - confidence is a heuristic, never a probability;
  - only the move-size probability is a probability;
  - every statistic is descriptive.

## Transferring the files without connecting this repository

Hand over only these files, for example as a ZIP made from the commit:

```bash
git -c core.autocrlf=false archive --format=zip -o dashboard-handoff.zip HEAD docs/api/dashboard
```

The archive contains only the files committed in this folder: no `.env`, no credentials, nothing else from the
repository. Lovable needs no access to this repository and no database credentials. After the transfer, compare the
file sizes, or the checksums above, to confirm nothing was cut off.
