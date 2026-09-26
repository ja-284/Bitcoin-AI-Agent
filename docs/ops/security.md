# Security audit — 2026-09-21

> **Superseded in one important respect — read this first.** This audit checked secrets, logs,
> workflow permissions and the trading boundary, and **never checked what the database exposes to
> Supabase's own public API**. On 2026-09-23 Supabase's advisor showed that every table was
> readable and writable by anyone holding the project's public anon key. That is now closed, with
> evidence, in [`security_2026-09-23_public_api_exposure.md`](security_2026-09-23_public_api_exposure.md).
> The text below is left as it was written, so the sequence stays honest.

Scope: a research-only backend that runs on GitHub Actions, writes to Supabase Postgres, and
calls Binance (public), RSS feeds (public), CoinGecko (free key), and the Anthropic API.
**It never trades, never holds funds, never touches an exchange account.** There is no web
server and no research endpoint: nothing listens.

## Secrets — where they live, where they must never be

| secret | lives in | used by | never in |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | GitHub Actions secret; local `.env` | news scorer, explainer | git, logs, rows, experiment records |
| `DATABASE_URL` (Supabase pooler, `postgres` role) | GitHub Actions secret; local `.env` | every DB call | git, logs (psycopg connection errors do not echo the DSN — checked), rows |
| `COINGECKO_API_KEY` (free demo key) | GitHub Actions secret; local `.env` | fallback provider header | git, logs |
| `HEARTBEAT_URL` (optional) | GitHub Actions secret | curl ping | git |
| `github_dispatch_token` (fine-grained PAT, `actions: write` on this repo only, **expires 2027-09-20**) | Supabase Vault | pg_cron → `workflow_dispatch` | git (`docs/ops/supabase_dispatch.sql` holds a placeholder), logs |

Checks performed: tracked files scanned for key-like strings (`sk-ant-`, `github_pat_`,
connection strings with passwords, JWTs, CoinGecko header values) — **none**; `.env` is
git-ignored and only `.env.example` (placeholders) is tracked; every stored row's `run_meta`,
`explanation` and `raw_indicators` scanned — **none**; experiment JSONs contain no
credentials; the Python code never logs `DATABASE_URL` or the API key (the only mention is
"DATABASE_URL is not set").

## GitHub Actions

- `permissions: contents: read` on both workflows (least privilege; the jobs never write to
  GitHub). Secrets are injected as environment variables, never echoed.
- Third-party actions are pinned to major versions (`actions/checkout@v4`,
  `actions/setup-python@v5`) — the standard trade-off between security and maintenance for a
  public repo; pinning to full SHAs is an option if the repo ever becomes sensitive.
  **Superseded 2026-09-26: every action is now pinned to a full commit SHA** (`checkout` v4 =
  `11d5960a…`, `setup-python` v5 = `a26af69b…`, each resolved two ways). The earlier reasoning
  underrated one fact: these actions run with the jobs' secrets (Anthropic key, database URL,
  heartbeat URL), so a repointed tag could exfiltrate them. `tests/test_workflow_pinning.py` fails on
  any movable reference; an upgrade is a deliberate edit of the SHA and its `# vN` comment. Verified on
  GitHub: the Tests run on `677e1c0` executed exactly the pinned commits.
- **Dependency vulnerabilities** (2026-09-26): `python tools/dependency_audit.py` queries OSV.dev for
  every installed package, direct and transitive (names and versions only). First run: **43 packages,
  0 known vulnerabilities.** Part of the weekly audit. Transitive packages are resolved fresh on each
  GitHub runner, so the local environment is audited as the closest available copy.
- The repo is public by decision (free unlimited Actions minutes; nothing proprietary).
  Consequence: anyone can read the code and the reports — none of which contains secrets or
  personal data.
- `workflow_dispatch` can be triggered by anyone holding a token with `actions: write` on the
  repo: only the fine-grained PAT in the Vault has it. A stray dispatch would at worst run one
  extra hourly job, which exits early if the hour already exists.

## Database

- The job connects as the project's `postgres` role through the pooler. **Not least
  privilege**: a dedicated role with `INSERT`/`SELECT` on the research tables (plus `UPDATE`
  of the shadow outcome columns) would be stricter. Mitigations in place: predictions and
  outcomes are append-only by trigger, shadow rows immutable except a one-time outcome, and
  the scratch-schema tests refuse to run unless every connection lands in the scratch schema.
  Creating a restricted role is a Supabase SQL change for the user to run; recommended, not
  urgent, and recorded as an open item.
- `pg_cron` + `pg_net` read the token from the Vault at run time; the job definition holds no
  secret. A 401 in `net._http_response` means the token is wrong or expired.
- Supabase free tier: auto-pause after 7 idle days (hourly writes prevent it).

## Logs and reports

Weekly reports (`research/monitoring/`) and experiment outputs contain prices, scores,
probabilities, timestamps, headlines and URLs — no credentials, no personal data. The
`code_commit` recorded in rows is a public SHA.

## Boundary

No order execution, wallet, exchange-account or payment code exists anywhere in the
repository, and none is planned. The only "actions" the system takes are: read public data,
call an LLM for a score and a text, write rows to its own database.

## Open items

1. Dedicated least-privilege database role (user action in Supabase; low urgency).
2. Healthchecks.io heartbeat (external alarm; `HEARTBEAT_URL` secret) — still not set up.
3. Regenerate the dispatch PAT before 2027-09-20.
